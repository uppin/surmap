"""`DemoWorkspace`: the default `SurveyWorkspace` adapter, over the demo's run host.

It drives the demo's `DemoRunHost` headlessly, reads the run history it records, and publishes
object geometry as GLB through a `GeometryStore`. The port and its types live in
`surmap.agent.tools.port` and are re-exported here.

Read/run only (docs/architecture.md section 1): a workspace launches demo runs and reads their
results; nothing here commands a vehicle or writes into RTAB-Map's map.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.agent.tools.geometry import GeometryStore
from surmap.agent.tools.port import (
    OBJECT_FRAME,
    OBJECT_UP_AXIS,
    BoxXYXY,
    FrameDetections,
    FrameImage,
    FrameRecord,
    FrameSource,
    ObjectBox,
    RunBusy,
    RunInfo,
    RunStatus,
    SceneInfo,
    StoredObject,
    SurveyWorkspace,
)
from surmap.demo.datasets import DatasetSpec, PreparedDataset, ensure_dataset
from surmap.demo.events import DemoEvent
from surmap.demo.gallery import GalleryEntry, dataset_thumbnail, gallery_entries
from surmap.demo.playback import PlaybackControls
from surmap.demo.runs import DemoRunHost, _RunEngine
from surmap.demo.server import DemoPlayer
from surmap.objects3d import write_glb
from surmap.survey.sam import RawFrame, VideoSamDetector

__all__ = [
    "OBJECT_FRAME",
    "OBJECT_UP_AXIS",
    "BoxXYXY",
    "DemoWorkspace",
    "FrameDetections",
    "FrameImage",
    "FrameRecord",
    "FrameSource",
    "GeometryStore",
    "ObjectBox",
    "RunBusy",
    "RunInfo",
    "RunStatus",
    "SceneInfo",
    "StoredObject",
    "SurveyWorkspace",
]

_SAM_TITLE = " · SAM: "
"""What the demo's run title puts between the scene title and the SAM concept it ran with."""

_OBJECT_ID = re.compile(r"obj_(\d+)")


@dataclass(frozen=True)
class _SurfacePiece:
    """One history row of a run's surface: the points one frame assigned to it."""

    surface_id: int
    label: str
    frame_id: int
    moving: bool
    points: NDArray[np.float32]


def _status_of(status: str) -> RunStatus:
    """The history's status as a run status; the history does not tell a cancel from a failure."""
    return {
        "running": RunStatus.RUNNING,
        "completed": RunStatus.FINISHED,
        "interrupted": RunStatus.CANCELLED,
    }.get(status, RunStatus.FAILED)


def _prompt_of(title: str) -> str:
    """The SAM concept a run was started with, from its title; empty when SAM was off."""
    _, separator, prompt = title.rpartition(_SAM_TITLE)
    return prompt if separator else ""


class DemoWorkspace:
    """`SurveyWorkspace` over the demo's run host, its history and its scene cache.

    Runs started here are ordinary demo runs in the host's history database, so the console
    lists them; a headless run takes over a running console run exactly as a new viewer would.
    `detector` answers `detect` on recorded frames. An object's id is `obj_<surface_id>` of the
    history's surface, and its points are every point the run assigned to that surface.
    """

    def __init__(
        self,
        host: DemoRunHost,
        *,
        detector: VideoSamDetector,
        geometry: GeometryStore,
    ) -> None:
        self._host = host
        self._detector = detector
        self._detector_lock = threading.Lock()
        self.geometry = geometry

    def datasets(self) -> Sequence[GalleryEntry]:
        prepared = {
            dataset_id: found
            for dataset_id in self._host.catalog
            if (found := self._host.prepared_scene(dataset_id)) is not None
        }
        return gallery_entries(self._host.cache_dir, catalog=self._host.catalog, prepared=prepared)

    def dataset(self, dataset_id: str) -> GalleryEntry | None:
        return next((entry for entry in self.datasets() if entry.dataset_id == dataset_id), None)

    def dataset_thumbnail(self, dataset_id: str) -> bytes | None:
        """The dataset's thumbnail JPEG, or None when it is not prepared."""
        if dataset_id not in self._host.catalog:
            return None
        prepared = self._host.prepared_scene(dataset_id)
        if prepared is None or not prepared.timestamps_ns:
            return None
        return dataset_thumbnail(prepared)

    async def prepare_dataset(self, dataset_id: str) -> GalleryEntry:
        spec = self._host.catalog[dataset_id]
        await asyncio.to_thread(self._prepared, spec)
        entry = self.dataset(dataset_id)
        if entry is None:  # the catalogue just answered with it
            raise RuntimeError(f"dataset {dataset_id} vanished from the catalogue")
        return entry

    async def run_rtabmap(
        self, dataset: str, *, max_frames: int | None, fps: float | None
    ) -> RunInfo:
        """RTAB-Map only: SAM sources disabled, the RTAB-Map backend forced on."""
        if fps is not None and fps <= 0:
            raise ValueError("fps must be positive")
        spec = self._host.catalog[dataset]
        prepared = await asyncio.to_thread(self._prepared, spec)
        return await self._run_recorded(
            prepared,
            None,
            max_frames=max_frames,
            fps=fps,
            overrides={"with_rtabmap": True, "sam_source": None, "sam_streamer": None},
            title_suffix=" · RTAB-Map",
        )

    async def run_sam_on_dataset(
        self, dataset: str, concept: str | None, *, max_frames: int | None
    ) -> Sequence[FrameDetections]:
        """SAM only: evenly spaced frames of the prepared dataset, no run recorded."""
        spec = self._host.catalog[dataset]
        prepared = await asyncio.to_thread(self._prepared, spec)
        prompt = concept or spec.sam_prompt
        count = min(max_frames or 8, 8, len(prepared.timestamps_ns))
        if count < 1:
            return ()
        stamps = prepared.timestamps_ns
        if count == 1:
            picks = [(0, stamps[0])]
        else:
            last = len(stamps) - 1
            picks = sorted(
                {
                    (round(step * last / (count - 1)), stamps[round(step * last / (count - 1))])
                    for step in range(count)
                }
            )
        frames: list[RawFrame] = []
        for index, t_ns in picks:
            path = prepared.frame_path(0, t_ns)
            with Image.open(path) as opened:
                rgb = opened.convert("RGB")
            frames.append(
                RawFrame(index + 1, t_ns, 0, rgb.width, rgb.height, "raw_rgb", rgb.tobytes())
            )
        with self._detector_lock:
            self._detector.reset(prompt)
            return tuple(
                FrameDetections(
                    frame_id=frame.frame_id,
                    t_ns=frame.t_ns,
                    detections=self._detector.track(frame),
                )
                for frame in frames
            )

    def scenes(self) -> Sequence[SceneInfo]:
        host = self._host
        return tuple(
            SceneInfo(
                id=spec.dataset_id,
                title=spec.title,
                default_prompt=host.sam_prompt(spec.dataset_id) or spec.sam_prompt,
                prepared=host.prepared_scene(spec.dataset_id) is not None,
                cached_run_id=host.history_store.latest_recording(spec.dataset_id),
            )
            for spec in host.catalog.values()
        )

    async def run_demo(
        self,
        dataset: str,
        prompt: str | None,
        *,
        max_frames: int | None,
        fps: float | None,
    ) -> RunInfo:
        if fps is not None and fps <= 0:
            raise ValueError("fps must be positive")
        spec = self._host.catalog[dataset]
        prepared = await asyncio.to_thread(self._prepared, spec)
        sam_prompt = self._host.sam_prompt(dataset, prompt)
        return await self._run_recorded(prepared, sam_prompt, max_frames=max_frames, fps=fps)

    async def _run_recorded(
        self,
        prepared: PreparedDataset,
        sam_prompt: str | None,
        *,
        max_frames: int | None,
        fps: float | None,
        overrides: dict[str, Any] | None = None,
        title_suffix: str = "",
    ) -> RunInfo:
        starting = asyncio.ensure_future(
            asyncio.to_thread(
                self._start, prepared, sam_prompt, max_frames, fps, overrides or {}, title_suffix
            )
        )
        try:
            engine = await asyncio.shield(starting)
        except asyncio.CancelledError:
            # The start runs on in its thread; a run it starts after the cancel is stopped too.
            started = await starting
            if started is not None:
                started.stop()
            raise
        if engine is None:
            raise RunBusy("the previous run did not stop in time, so no new run started")
        try:
            await asyncio.to_thread(engine.done.wait)
        except asyncio.CancelledError:
            engine.stop()
            raise
        run = self.run(engine.run_id)
        if run is None:
            raise RuntimeError(f"run {engine.run_id} is missing from the history")
        return run

    def run(self, run_id: str) -> RunInfo | None:
        row = self._host.history_store.get_run(run_id)
        if row is None:
            return None
        return RunInfo(
            run_id=run_id,
            dataset=str(row["dataset_id"]),
            prompt=_prompt_of(str(row["title"])),
            frames=int(str(row["frame_count"])),
            objects=len(self.objects(run_id)),
            status=_status_of(str(row["status"])),
        )

    def timeline(self, run_id: str) -> Sequence[FrameRecord]:
        return tuple(
            FrameRecord(
                index=index,
                frame_id=int(str(row["frame_id"])),
                t_ns=int(str(row["t_ns"])),
            )
            for index, row in enumerate(self._host.history_store.timeline(run_id))
        )

    async def detect(
        self, run_id: str, concept: str, frame_ids: Sequence[int]
    ) -> Sequence[FrameDetections]:
        return await asyncio.to_thread(self._segment, run_id, concept, tuple(frame_ids))

    def objects(self, run_id: str) -> Sequence[StoredObject]:
        times = {record.frame_id: record.t_ns for record in self.timeline(run_id)}
        pieces_by_surface: dict[int, list[_SurfacePiece]] = {}
        for piece in self._surface_pieces(run_id):
            pieces_by_surface.setdefault(piece.surface_id, []).append(piece)
        objects: list[StoredObject] = []
        for surface_id in sorted(pieces_by_surface):
            pieces = pieces_by_surface[surface_id]
            points = np.concatenate([piece.points for piece in pieces])
            if len(points) == 0:
                continue
            frame_ids = tuple(sorted({piece.frame_id for piece in pieces}))
            seen = [times[frame_id] for frame_id in frame_ids if frame_id in times]
            objects.append(
                StoredObject(
                    object_id=f"obj_{surface_id}",
                    label=pieces[0].label,
                    points=points,
                    moving=any(piece.moving for piece in pieces),
                    frame_ids=frame_ids,
                    t_first_ns=min(seen) if seen else None,
                    t_last_ns=max(seen) if seen else None,
                )
            )
        return tuple(objects)

    def object_box(self, run_id: str, object_id: str, frame_id: int) -> ObjectBox | None:
        match = _OBJECT_ID.fullmatch(object_id)
        if match is None:
            return None
        track_id = self._track_of(run_id, int(match.group(1)), frame_id)
        if track_id is None:
            return None
        history = self._host.history_store
        jpeg = history.frame_jpeg(run_id, frame_id)
        sam = history.sam_at(run_id, frame_id)
        if jpeg is None or sam is None or int(str(sam["frame_id"])) != frame_id:
            return None
        for found in cast(list[dict[str, object]], sam["objects"]):
            if found.get("track_id") != track_id:
                continue
            x0, y0, x1, y1 = (float(value) for value in cast(list[float], found["box"]))
            with Image.open(io.BytesIO(jpeg)) as display:
                measured_on = (display.width, display.height)
            return ObjectBox(box_xyxy=(x0, y0, x1, y1), measured_on=measured_on)
        return None

    def frame(self, run_id: str, frame_id: int) -> FrameImage | None:
        history = self._host.history_store
        row = history.get_run(run_id)
        if row is None:
            return None
        record = next((r for r in self.timeline(run_id) if r.frame_id == frame_id), None)
        if record is None:
            return None
        full = self._full_frame_path(str(row["dataset_id"]), record.t_ns)
        if full is not None:
            data = full.read_bytes()
            source, media_type = FrameSource.FULL, "image/png"
        else:
            jpeg = history.frame_jpeg(run_id, frame_id)
            if jpeg is None:
                return None
            data, source, media_type = jpeg, FrameSource.DISPLAY, "image/jpeg"
        with Image.open(io.BytesIO(data)) as opened:
            width, height = opened.size
        return FrameImage(
            frame_id=frame_id,
            t_ns=record.t_ns,
            data=data,
            media_type=media_type,
            width=width,
            height=height,
            source=source,
        )

    def publish_geometry(self, run_id: str, obj: StoredObject) -> str:
        if self.geometry.has(run_id, obj.object_id):
            return self.geometry.uri(run_id, obj.object_id)
        glb = write_glb(obj.points, frame=OBJECT_FRAME, up_axis=OBJECT_UP_AXIS)
        return self.geometry.put(run_id, obj.object_id, glb)

    def _prepared(self, spec: DatasetSpec) -> PreparedDataset:
        found = self._host.prepared_scene(spec.dataset_id)
        if found is not None:
            return found
        prepared = ensure_dataset(spec, self._host.cache_dir, fetch=self._host.fetch)
        with self._host.state_lock:
            self._host.prepared[spec.dataset_id] = prepared
        return prepared

    def _start(
        self,
        prepared: PreparedDataset,
        sam_prompt: str | None,
        max_frames: int | None,
        fps: float | None,
        overrides: dict[str, Any] | None = None,
        title_suffix: str = "",
    ) -> _RunEngine | None:
        # The host's player options are one untyped bag; this call's rate, frame cap
        # and per-mode overrides replace the host-wide ones for this run only.
        options: dict[str, Any] = {
            **self._host.player_options,
            "fps": fps,
            "max_frames": max_frames or 0,
            **(overrides or {}),
        }
        title = (
            prepared.spec.title + (f"{_SAM_TITLE}{sam_prompt}" if sam_prompt else "") + title_suffix
        )

        def play(controls: PlaybackControls) -> Iterator[DemoEvent]:
            player = DemoPlayer(prepared, controls=controls, sam_prompt=sam_prompt, **options)
            return player.events()

        return self._host._take_over(
            lambda: _RunEngine(self._host, prepared.spec.dataset_id, title, play)
        )

    def _full_frame_path(self, dataset_id: str, t_ns: int) -> Path | None:
        if dataset_id not in self._host.catalog:
            return None
        prepared = self._host.prepared_scene(dataset_id)
        if prepared is None:
            return None
        path = prepared.frame_path(0, t_ns)
        return path if path.is_file() else None

    def _segment(
        self, run_id: str, concept: str, frame_ids: tuple[int, ...]
    ) -> tuple[FrameDetections, ...]:
        frames = [self._raw_frame(run_id, frame_id) for frame_id in frame_ids]
        with self._detector_lock:
            self._detector.reset(concept)
            return tuple(
                FrameDetections(
                    frame_id=frame.frame_id,
                    t_ns=frame.t_ns,
                    detections=self._detector.track(frame),
                )
                for frame in frames
            )

    def _raw_frame(self, run_id: str, frame_id: int) -> RawFrame:
        image = self.frame(run_id, frame_id)
        if image is None:
            raise KeyError(f"run {run_id} has no frame {frame_id}")
        with Image.open(io.BytesIO(image.data)) as opened:
            rgb = opened.convert("RGB")
        return RawFrame(
            image.frame_id, image.t_ns, 0, rgb.width, rgb.height, "raw_rgb", rgb.tobytes()
        )

    def _surface_pieces(self, run_id: str) -> list[_SurfacePiece]:
        with self._host.history_store.exclusive() as db:
            rows = db.execute(
                "SELECT surface_id, label, frame_id, moving, points"
                " FROM surface_points WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [
            _SurfacePiece(
                surface_id=int(row["surface_id"]),
                label=str(row["label"]),
                frame_id=int(row["frame_id"]),
                moving=bool(row["moving"]),
                points=np.asarray(json.loads(str(row["points"])), dtype=np.float32).reshape(-1, 3),
            )
            for row in rows
        ]

    def _track_of(self, run_id: str, surface_id: int, frame_id: int) -> int | None:
        """The SAM track the surface was assigned from on `frame_id`, if it was on it."""
        with self._host.history_store.exclusive() as db:
            row = db.execute(
                "SELECT track_id FROM surface_points"
                " WHERE run_id = ? AND surface_id = ? AND frame_id = ? ORDER BY id LIMIT 1",
                (run_id, surface_id, frame_id),
            ).fetchone()
        return int(row["track_id"]) if row is not None else None
