from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from surmap.demo.cloud_view import CloudPose as CloudPose
from surmap.demo.cloud_view import CloudViewer, FollowCamera
from surmap.demo.datasets import (
    DatasetSpec,
    PreparedDataset,
    PrepareProgress,
    cached_dataset,
    ensure_dataset,
)
from surmap.demo.events import JOURNAL_ONLY, dense_frame_of
from surmap.demo.events import DemoEvent as DemoEvent
from surmap.demo.history import RunHistoryStore
from surmap.demo.playback import PlaybackControls as PlaybackControls
from surmap.demo.replay import JournalPlayer
from surmap.demo.sam_journal import JournalSamDetector
from surmap.demo.sam_prompt import SamPromptPolicy
from surmap.demo.surface_render import SurfaceLayer
from surmap.demo.surface_timeline import SurfaceTimelines


class _RunEngine:
    """One scene's server-side playback.

    The player runs in this engine's own thread: it exchanges frames
    with the CM5/Station servers and records the run's history there,
    never inside a browser's request. Browsers subscribe to the
    events it publishes and only render them; publishing drops
    intermediates for a subscriber that falls behind, so a slow or
    vanished client cannot slow the server-side exchange.
    """

    def __init__(
        self,
        server: DemoRunHost,
        dataset_id: str,
        title: str,
        play: Callable[[PlaybackControls], Iterator[DemoEvent]],
        *,
        replay_of: str | None = None,
        record: bool = True,
    ) -> None:
        if not record and replay_of is None:
            raise ValueError("only a replay can run unrecorded")
        self._server = server
        self.dataset_id = dataset_id
        self._title = title
        self._play_events = play
        self.replay_of = replay_of
        # An unrecorded rerun persists nothing: viewers see the recording itself.
        self.record = record
        self.controls = PlaybackControls(server.cloud_viewer)
        self.run_id = ""
        self.done = threading.Event()
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue[DemoEvent | None]] = set()
        self._latest: dict[str, DemoEvent] = {}
        self._thread = threading.Thread(target=self._play, daemon=True)

    def start(self) -> None:
        store = self._server.history_store
        if not self.record:
            assert self.replay_of is not None
            self.run_id = self.replay_of
        else:
            self.run_id = store.create_run(self.dataset_id, self._title)
            if self.replay_of is not None:
                store.record_source(self.run_id, self.replay_of)
        self._latest["run"] = DemoEvent(
            "run",
            {"run_id": self.run_id, "dataset_id": self.dataset_id, "replay_of": self.replay_of},
        )
        self._thread.start()

    def subscribe(self) -> queue.Queue[DemoEvent | None]:
        """A new renderer's queue, preloaded with the current state."""
        subscriber: queue.Queue[DemoEvent | None] = queue.Queue(maxsize=512)
        with self._lock:
            self._subscribers.add(subscriber)
            for kind in ("run", "status", "frame", "map", "sam", "final"):
                if kind in self._latest:
                    subscriber.put_nowait(self._latest[kind])
            if self.done.is_set():
                subscriber.put_nowait(None)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[DemoEvent | None]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def stop(self) -> None:
        """Takeover: cancel playback and end every subscription."""
        self.controls.cancel()
        self._finish_subscribers()

    def join(self, timeout: float) -> bool:
        if self._thread.ident is None:
            return True  # created but never started: nothing to stop
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @staticmethod
    def _offer(subscriber: queue.Queue[DemoEvent | None], event: DemoEvent | None) -> None:
        try:
            subscriber.put_nowait(event)
            return
        except queue.Full:
            pass
        try:
            subscriber.get_nowait()  # drop the stalest rendered state
        except queue.Empty:
            pass
        try:
            subscriber.put_nowait(event)
        except queue.Full:
            pass

    def _publish(self, event: DemoEvent) -> None:
        with self._lock:
            if event.kind != "run":
                self._latest[event.kind] = event
            for subscriber in self._subscribers:
                self._offer(subscriber, event)

    def _finish_subscribers(self) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for subscriber in subscribers:
            self._offer(subscriber, None)

    def _record(
        self, event: DemoEvent, last_frame_id: int, last_map: dict[str, object]
    ) -> tuple[int, dict[str, object]]:
        """Persist one event into the run's history; returns the map state it carries."""
        store = self._server.history_store
        if event.kind == "rig":
            store.record_rig(self.run_id, event.data)
        elif event.kind == "dense":
            store.record_dense(self.run_id, dense_frame_of(event))
        else:
            store.record_event(self.run_id, event.kind, event.data)
        if event.kind == "frame" and event.jpeg:
            last_frame_id = int(str(event.data["frame_id"]))
            overlay_raw = event.data["detections"]
            camera_raw = event.data.get("camera")
            store.record_frame(
                self.run_id,
                index=int(str(event.data["index"])),
                frame_id=last_frame_id,
                t_ns=int(str(event.data["t_ns"])),
                jpeg=event.jpeg,
                overlay=overlay_raw if isinstance(overlay_raw, list) else [],
                camera=camera_raw if isinstance(camera_raw, dict) else None,
            )
        elif event.kind == "map":
            last_frame_id = int(str(event.data["frame_id"]))
            last_map = dict(event.data)
            _record_map(store, self.run_id, event.data, last_frame_id)
        elif event.kind == "surface":
            store.record_surface_event(self.run_id, event.data)
        elif event.kind == "detections":
            objects_raw = event.data["objects"]
            store.record_detections(
                self.run_id,
                frame_id=int(str(event.data["frame_id"])),
                t_ns=int(str(event.data["t_ns"])),
                objects=objects_raw if isinstance(objects_raw, list) else [],
            )
        elif event.kind == "final":
            # The final cloud keeps the last map's keyframe/odom stats.
            _record_map(store, self.run_id, {**last_map, **event.data}, last_frame_id)
        return last_frame_id, last_map

    def _play(self) -> None:
        server = self._server
        store = server.history_store
        completed = False
        last_frame_id = 0
        last_map: dict[str, object] = {}
        try:
            for event in self._play_events(self.controls):
                if self.record:
                    last_frame_id, last_map = self._record(event, last_frame_id, last_map)
                if event.kind == "final":
                    completed = True
                if event.kind not in JOURNAL_ONLY:
                    self._publish(event)
            # A player cancelled by a takeover returns early: cut short,
            # that run is no complete recording to rerun.
            completed = not self.controls.cancelled
        except Exception:
            completed = False
        finally:
            if self.record:
                store.finish_run(self.run_id, "completed" if completed else "interrupted")
            self.done.set()
            self._finish_subscribers()
            with server.state_lock:
                if server.run_engine is self:
                    server.run_engine = None
                if server.current is self.controls:
                    server.current = None


def _record_map(
    store: RunHistoryStore, run_id: str, data: dict[str, object], frame_id: int
) -> None:
    points = data.get("points")
    colors = data.get("point_colors")
    trajectory = data.get("trajectory_xy")
    extent = data.get("extent")
    store.record_map(
        run_id,
        frame_id=frame_id,
        points=points if isinstance(points, list) else [],
        colors=colors if isinstance(colors, list) else [],
        trajectory_xy=trajectory if isinstance(trajectory, list) else [],
        extent=extent if isinstance(extent, list) else [],
        cloud_points=int(str(data.get("cloud_points", 0))),
        keyframes=int(str(data.get("keyframes", 0))),
        odom_state=str(data.get("odom_state", "")),
    )


# A new viewer waits at most this long for the running stream to stop.
TAKEOVER_TIMEOUT_S = 10.0


@dataclass
class _Preparation:
    """One scene's background download + extraction into the cache."""

    state: str = "preparing"  # preparing | ready | error
    progress: PrepareProgress | None = None
    error: str = ""


class DemoRunHost:
    """The demo's runs and scenes, with no HTTP attached; `_DemoHttpServer` serves it."""

    catalog: dict[str, DatasetSpec]
    default_dataset: str
    cache_dir: Path
    fetch: Callable[[str, Path], None] | None
    player_options: dict[str, object]
    cm5_enabled: bool
    station_execution: str
    sam_enabled: bool
    sam_prompts: SamPromptPolicy
    run_lock: threading.Lock
    state_lock: threading.Lock
    prepared: dict[str, PreparedDataset]
    preparations: dict[str, _Preparation]
    current: PlaybackControls | None
    cloud_viewer: CloudViewer  # the session's 3D view, shared by every run
    surface_timelines: SurfaceTimelines  # rewound moments' surfaces, today's logic
    run_engine: _RunEngine | None
    history_store: RunHistoryStore

    def start_run(
        self,
        prepared: PreparedDataset,
        sam_prompt: str | None,
        *,
        sam_from: str | None = None,
    ) -> _RunEngine | None:
        """Start a fresh live server-side run, taking over from the current one.

        With `sam_from`, SAM is not run: that recorded run's journalled
        masks answer each frame (`surmap.demo.sam_journal`), so only the
        RTAB-Map part is rebuilt. The previous run (if any) is cancelled
        and its subscribers ended; None when it does not stop in time.
        """
        title = prepared.spec.title + (f" · SAM: {sam_prompt}" if sam_prompt else "")
        options = self.player_options
        if sam_from is not None:
            source = self.history_store.get_run(sam_from)
            assert source is not None
            title = f"{source['title']} · RTAB-Map rebuilt from {sam_from[:8]}"
            options = {
                **options,
                "sam_source": JournalSamDetector(self.history_store, sam_from),
                "sam_streamer": None,
            }

        def play(controls: PlaybackControls) -> Iterator[DemoEvent]:
            from surmap.demo.server import DemoPlayer

            player = DemoPlayer(
                prepared,
                controls=controls,
                sam_prompt=sam_prompt,
                **options,  # type: ignore[arg-type]
            )
            return player.events()

        return self._take_over(lambda: _RunEngine(self, prepared.spec.dataset_id, title, play))

    def start_replay(self, run_id: str, speed: float, record: bool = True) -> _RunEngine | None:
        """Replay `run_id` from its journal (see `start_run`).

        `speed` multiplies the scene's frame rate; 0 plays as fast as
        possible. Recorded, the replay is a new run naming its source;
        unrecorded (the console's default rerun) it persists nothing.
        """
        source = self.history_store.get_run(run_id)
        assert source is not None
        dataset_id = str(source["dataset_id"])
        spec = self.catalog.get(dataset_id)
        fps = (spec.fps if spec is not None else 10.0) * speed
        store = self.history_store

        def play(controls: PlaybackControls) -> Iterator[DemoEvent]:
            def render(
                points: NDArray[np.float32],
                colors: NDArray[np.uint8],
                bounds: tuple[NDArray[np.float32], NDArray[np.float32]],
                layer: SurfaceLayer,
                camera: FollowCamera | None,
            ) -> dict[str, str]:
                return controls.viewer.render_view(points, colors, bounds, layer, camera)

            return JournalPlayer(
                store, run_id, controls=controls, fps=fps, render_cloud=render
            ).events()

        title = f"Replay of {source['title']}"
        return self._take_over(
            lambda: _RunEngine(self, dataset_id, title, play, replay_of=run_id, record=record)
        )

    def _take_over(self, create: Callable[[], _RunEngine]) -> _RunEngine | None:
        with self.run_lock:
            with self.state_lock:
                previous = self.run_engine
            if previous is not None and not previous.done.is_set():
                previous.stop()
                if not previous.join(TAKEOVER_TIMEOUT_S):
                    return None
            engine = create()
            engine.start()
            with self.state_lock:
                self.run_engine = engine
                if not engine.done.is_set():
                    self.current = engine.controls
            if engine.done.is_set():
                # It finished before it could be registered; its own
                # cleanup already ran, so unregister it again.
                with self.state_lock:
                    if self.run_engine is engine:
                        self.run_engine = None
                    if self.current is engine.controls:
                        self.current = None
            return engine

    def prepared_scene(self, dataset_id: str) -> PreparedDataset | None:
        with self.state_lock:
            found = self.prepared.get(dataset_id)
        if found is None:
            found = cached_dataset(self.catalog[dataset_id], self.cache_dir)
            if found is not None:
                with self.state_lock:
                    self.prepared[dataset_id] = found
        return found

    def sam_prompt(self, dataset_id: str, requested: str | None = None) -> str | None:
        """The concept SAM looks for on this run, or None without SAM."""
        if not self.sam_enabled:
            return None
        return self.sam_prompts.resolve(requested, self.catalog[dataset_id].sam_prompt)

    def scene_listing(self) -> dict[str, object]:
        scenes = []
        for dataset_id, spec in self.catalog.items():
            entry: dict[str, object] = {
                "id": dataset_id,
                "title": spec.title,
                "description": spec.description,
                "state": "missing",
                "progress": None,
                "error": "",
                # What the page reruns by default (None: only Rebuild plays it).
                "cached_run": self.history_store.latest_recording(dataset_id),
            }
            with self.state_lock:
                job = self.preparations.get(dataset_id)
            if self.prepared_scene(dataset_id) is not None:
                entry["state"] = "ready"
                entry["progress"] = {"phase": "ready", "done": 1, "total": 1}
            elif job is not None:
                step = job.progress
                entry["state"] = job.state
                entry["error"] = job.error
                if step is not None:
                    entry["progress"] = {
                        "phase": step.phase,
                        "done": step.done,
                        "total": step.total,
                    }
            scenes.append(entry)
        return {"current": self.default_dataset, "datasets": scenes}

    def prepare(self, dataset_id: str) -> str:
        """Start preparing `dataset_id` once (idempotent); its state now."""
        if self.prepared_scene(dataset_id) is not None:
            return "ready"
        with self.state_lock:
            job = self.preparations.get(dataset_id)
            if job is not None and job.state == "preparing":
                return job.state
            job = _Preparation()
            self.preparations[dataset_id] = job
        threading.Thread(target=self._prepare, args=(dataset_id, job), daemon=True).start()
        return job.state

    def _prepare(self, dataset_id: str, job: _Preparation) -> None:
        def report(step: PrepareProgress) -> None:
            job.progress = step

        try:
            prepared = ensure_dataset(
                self.catalog[dataset_id], self.cache_dir, fetch=self.fetch, progress=report
            )
        except Exception as exc:  # surfaced to the page via /datasets
            job.state, job.error = "error", str(exc)
            return
        with self.state_lock:
            self.prepared[dataset_id] = prepared
        job.state = "ready"
