"""The station's per-drone perception: only the active drone's stream is processed, each drone
into its own map.

A fleet page streams the active drone's stereo pairs to the bridge (`bevy_bridge`), each pair
labelled with its drone (`BevyPair.drone_id`; a pair without one is the `default` drone, as a
single-drone page or a recorded capture sends). `FleetPerception` is one page connection: it
routes each pair to that drone's `DroneSession` — an RTAB-Map backend from the factory, a
segmentation run on its left frames, an optional recorder, and counts — created the first time
the drone's frames arrive. A drone whose frames stop is idle: its backend and map stay alive,
and its frames, when they come again, go to the same backend. At most `MAX_DRONE_SESSIONS`
sessions exist per connection; a further drone's pairs are answered with a status naming the
limit and processed by nothing. Closing the connection finishes every session.

`PerceptionRegistry` finds a scenario's connected page for the agent's `drone_map_status` tool.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol, cast

import numpy as np
from PIL import Image

from surmap.simulation.bevy_bridge import BackendFactory, PairRecorder, StreamingBackend
from surmap.simulation.bevy_wire import (
    BevyHello,
    BevyPair,
    BevyWireError,
    BridgeStatus,
    FrameKeypoints,
    decode_bevy_message,
)
from surmap.simulation.camera_profile import profile_sensor_yaml
from surmap.slam.keypoint_pixels import rectified_to_raw
from surmap.slam.stream_protocol import MapUpdate, OdomUpdate, Rectification
from surmap.survey.sam import RawFrame, SamDetector
from surmap.types import StereoFramePair

__all__ = [
    "DEFAULT_DRONE",
    "MAX_DRONE_SESSIONS",
    "SAM_QUEUE_SIZE",
    "DroneCounts",
    "DroneSession",
    "FleetPerception",
    "PerceptionRegistry",
    "RecorderFactory",
    "SamSegmentationSink",
    "SegmentationFactory",
    "SegmentationSink",
]

MAX_DRONE_SESSIONS: Final = 4
"""Live drone sessions (one RTAB-Map sidecar each) per page connection."""

DEFAULT_DRONE: Final = "default"
"""The drone a pair without a drone id belongs to."""

SAM_QUEUE_SIZE: Final = 2
"""Left frames waiting for the detector; a newer frame drops the oldest."""


class SegmentationSink(Protocol):
    """One drone's segmentation run: its left frames in, counted."""

    @property
    def segmented_frames(self) -> int: ...

    @property
    def detections(self) -> int: ...

    def submit(self, left: RawFrame) -> None: ...

    def close(self) -> None: ...


SegmentationFactory = Callable[[str], SegmentationSink]
"""Builds a drone's segmentation run, by drone id."""

RecorderFactory = Callable[[str], PairRecorder]
"""Builds a drone's capture recorder, by drone id."""


@dataclass(frozen=True)
class DroneCounts:
    """One drone's session as `drone_map_status` reports it."""

    drone_id: str
    frames: int
    posed: int
    lost: int
    """Odometry updates that reported tracking lost."""
    keyframes: int
    dropped: int
    segmented_frames: int
    detections: int
    processing: bool
    """Whether this drone's frames are the ones being processed now."""
    last_t_ns: int | None
    """The simulation time of its last processed frame; `None` before any."""
    error: str | None = None
    """Why its map stopped (the backend failed); `None` while it runs."""


class DroneSession:
    """One drone's live map: its backend, its segmentation run, its optional recorder, and the
    counts its frames have produced."""

    def __init__(
        self,
        drone_id: str,
        backend: StreamingBackend,
        segmentation: SegmentationSink,
        recorder: PairRecorder | None = None,
    ) -> None:
        self.drone_id = drone_id
        self.backend = backend
        self.segmentation = segmentation
        self.recorder = recorder
        self._backend_open = True
        self._frames = 0
        self._posed = 0
        self._lost = 0
        self._lost_now = False
        self._last_t_ns: int | None = None
        self._error: str | None = None
        self._odometry: tuple[FrameKeypoints, ...] = ()

    @property
    def error(self) -> str | None:
        """Why this session stopped; `None` while it runs. An errored session takes no more
        pairs, and its counts stay as they were."""
        return self._error

    def process(self, pair: BevyPair, calibration_id: str) -> None:
        """Records `pair`, feeds it to the backend as a stereo frame, submits its left frame to
        segmentation, and counts the backend's odometry updates. A failure of any of that marks
        the session errored (its backend is closed, once) instead of escaping, so the drone's
        failure stays this session's; an errored session ignores later pairs."""
        if self._error is not None:
            return
        try:
            self._process(pair, calibration_id)
        except Exception as failure:
            self._error = f"{type(failure).__name__}: {failure}"
            with contextlib.suppress(Exception):  # the map is already failing; its error stands
                self._close_backend()

    def _close_backend(self) -> None:
        if self._backend_open:
            self._backend_open = False
            self.backend.close()

    def _process(self, pair: BevyPair, calibration_id: str) -> None:
        if self.recorder is not None:
            self.recorder.record_pair(pair)
        self.backend.process_frame(
            StereoFramePair(
                frame_id=pair.frame_id,
                t_ns=pair.t_ns,
                left_ref="",
                right_ref="",
                calibration_id=calibration_id,
                left_data=_png(pair.left_data, pair.width, pair.height),
                right_data=_png(pair.right_data, pair.width, pair.height),
            )
        )
        self.segmentation.submit(
            RawFrame(
                frame_id=pair.frame_id,
                t_ns=pair.t_ns,
                channel=0,
                width=pair.width,
                height=pair.height,
                encoding=pair.encoding,
                data=pair.left_data,
            )
        )
        self._frames += 1
        self._last_t_ns = pair.t_ns
        odometry: list[FrameKeypoints] = []
        for update in cast("list[MapUpdate]", self.backend.poll_updates()):
            if not isinstance(update, OdomUpdate):
                continue
            odometry.append(
                frame_keypoints(update, self.backend.rectification, pair.width, pair.height)
            )
            if update.pose is not None:
                self._posed += 1
            if update.lost:
                self._lost += 1
            self._lost_now = update.lost
        self._odometry = tuple(odometry)

    def status(self) -> BridgeStatus:
        """The status reply for this drone's last pair."""
        return BridgeStatus(
            frames=self._frames,
            posed=self._posed,
            lost=self._lost_now,
            keyframes=self.backend.keyframe_count,
            dropped=self.backend.dropped_frames,
            drone_id=None if self.drone_id == DEFAULT_DRONE else self.drone_id,
            error=self._error,
            odometry=self._odometry,
        )

    def counts(self, *, processing: bool) -> DroneCounts:
        """This session's counts; `processing` marks it the drone being processed now."""
        return DroneCounts(
            drone_id=self.drone_id,
            frames=self._frames,
            posed=self._posed,
            lost=self._lost,
            keyframes=self.backend.keyframe_count,
            dropped=self.backend.dropped_frames,
            segmented_frames=self.segmentation.segmented_frames,
            detections=self.segmentation.detections,
            processing=processing,
            last_t_ns=self._last_t_ns,
            error=self._error,
        )

    def close(self) -> None:
        """Closes the backend (unless a failure already did) and the segmentation run, and
        finishes the recorder."""
        self._close_backend()
        self.segmentation.close()
        if self.recorder is not None:
            self.recorder.finish()


def frame_keypoints(
    update: OdomUpdate, rectification: Rectification | None, width: int, height: int
) -> FrameKeypoints:
    """`update`'s tracked keypoints at their raw pixels in the `width` x `height` left frame
    (rectified ones mapped back through `rectification`); those outside the frame are left out."""
    if not update.keypoints:
        return FrameKeypoints(update.frame_id, ())
    pixels = np.array([(k.u, k.v) for k in update.keypoints], dtype=np.float64)
    if rectification is not None:
        pixels = rectified_to_raw(pixels, rectification)
    return FrameKeypoints(
        update.frame_id,
        tuple(
            (round(u, 1), round(v, 1), round(k.depth, 2))
            for (u, v), k in zip(pixels.tolist(), update.keypoints, strict=True)
            if 0 <= u < width and 0 <= v < height
        ),
    )


def _png(gray: bytes, width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.frombytes("L", (width, height), gray).save(buffer, format="PNG")
    return buffer.getvalue()


class FleetPerception:
    """One bridge connection's drone sessions, keyed by drone id: a `bevy_bridge.BridgeSession`.

    `hello` keeps the camera profile and the scenario, and registers this connection in
    `registry` under the scenario; each `pair` goes to its drone's session (created through the
    factories, at most `max_sessions`), which becomes the processing drone; `close` finishes
    every session in drone-id order and unregisters the connection.
    """

    def __init__(
        self,
        backend_factory: BackendFactory,
        segmentation_factory: SegmentationFactory,
        *,
        registry: PerceptionRegistry | None = None,
        recorder_factory: RecorderFactory | None = None,
        max_sessions: int = MAX_DRONE_SESSIONS,
    ) -> None:
        self._backend_factory = backend_factory
        self._segmentation_factory = segmentation_factory
        self._registry = registry
        self._recorder_factory = recorder_factory
        self._max_sessions = max_sessions
        self._hello: BevyHello | None = None
        self._sessions: dict[str, DroneSession] = {}
        self._processing: str | None = None

    def handle(self, message: bytes) -> BridgeStatus:
        """One wire message in, its status reply out. A pair before any hello is a
        `BevyWireError`."""
        decoded = decode_bevy_message(message)
        if isinstance(decoded, BevyHello):
            self._hello = decoded
            if self._registry is not None and decoded.scenario is not None:
                self._registry.register(decoded.scenario, self)
            return BridgeStatus(frames=0, posed=0, lost=False, keyframes=0, dropped=0)
        if self._hello is None:
            raise BevyWireError("pair received before any hello")
        pair = decoded
        drone_id = pair.drone_id if pair.drone_id is not None else DEFAULT_DRONE
        session = self._sessions.get(drone_id)
        if session is None:
            if len(self._sessions) >= self._max_sessions:
                return BridgeStatus(
                    frames=0,
                    posed=0,
                    lost=False,
                    keyframes=0,
                    dropped=0,
                    drone_id=pair.drone_id,
                    error=(
                        f"drone session limit ({self._max_sessions}) reached; "
                        f"{drone_id} not processed"
                    ),
                )
            camera = self._hello.camera
            session = DroneSession(
                drone_id,
                self._backend_factory(
                    cam0_yaml=profile_sensor_yaml(camera, 0),
                    cam1_yaml=profile_sensor_yaml(camera, 1),
                    width=camera.width,
                    height=camera.height,
                ),
                self._segmentation_factory(drone_id),
                self._recorder_factory(drone_id) if self._recorder_factory is not None else None,
            )
            self._sessions[drone_id] = session
        session.process(pair, self._hello.camera.id)
        self._processing = drone_id
        return session.status()

    def counts(self) -> tuple[DroneCounts, ...]:
        """Every drone session's counts, in drone-id order."""
        return tuple(
            self._sessions[drone_id].counts(processing=drone_id == self._processing)
            for drone_id in sorted(self._sessions)
        )

    def processing(self) -> str | None:
        """The drone whose frame was processed last; `None` before any."""
        return self._processing

    def close(self) -> None:
        """Finishes every drone session, in drone-id order, and unregisters the connection."""
        sessions, self._sessions = self._sessions, {}
        for drone_id in sorted(sessions):
            sessions[drone_id].close()
        if (
            self._registry is not None
            and self._hello is not None
            and self._hello.scenario is not None
        ):
            self._registry.unregister(self._hello.scenario, self)


class SamSegmentationSink:
    """A `SegmentationSink` over the station's `SamDetector`: a worker thread runs the detector
    on each submitted left frame, `queue_size` frames waiting at most (a newer frame drops the
    oldest); counts frames segmented, detections and frames dropped. `close` lets the waiting
    frames finish, then stops the worker."""

    def __init__(self, detector: SamDetector, *, queue_size: int = SAM_QUEUE_SIZE) -> None:
        self._detector = detector
        self._queue: queue.Queue[RawFrame | None] = queue.Queue(maxsize=max(1, queue_size))
        self._lock = threading.Lock()
        self._segmented_frames = 0
        self._detections = 0
        self._dropped_frames = 0
        self._closed = False
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    @property
    def segmented_frames(self) -> int:
        with self._lock:
            return self._segmented_frames

    @property
    def detections(self) -> int:
        with self._lock:
            return self._detections

    @property
    def dropped_frames(self) -> int:
        with self._lock:
            return self._dropped_frames

    def submit(self, left: RawFrame) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._queue.put_nowait(left)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self._dropped_frames += 1
                except queue.Empty:
                    pass
                self._queue.put_nowait(left)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._queue.put(None)
        self._worker.join()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            while True:
                frame = self._queue.get()
                if frame is None:
                    return
                try:
                    found = loop.run_until_complete(self._detector.detect(frame))
                except Exception:
                    continue
                with self._lock:
                    self._segmented_frames += 1
                    self._detections += len(found)
        finally:
            loop.close()


class PerceptionRegistry:
    """The connected bridge pages, by the scenario their `hello` names; the latest page of a
    scenario wins."""

    def __init__(self) -> None:
        self._pages: dict[str, FleetPerception] = {}

    def register(self, scenario_id: str, perception: FleetPerception) -> None:
        self._pages[scenario_id] = perception

    def unregister(self, scenario_id: str, perception: FleetPerception) -> None:
        """Forgets `perception` if it is still the scenario's page."""
        if self._pages.get(scenario_id) is perception:
            del self._pages[scenario_id]

    def perception(self, scenario_id: str) -> FleetPerception | None:
        """The scenario's connected page; `None` when no page streams it."""
        return self._pages.get(scenario_id)
