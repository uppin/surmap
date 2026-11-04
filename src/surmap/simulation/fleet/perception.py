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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

from surmap.simulation.bevy_bridge import BackendFactory, PairRecorder, StreamingBackend
from surmap.simulation.bevy_wire import BevyPair, BridgeStatus
from surmap.survey.sam import RawFrame, SamDetector

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

    def process(self, pair: BevyPair, calibration_id: str) -> None:
        """Records `pair`, feeds it to the backend as a stereo frame, submits its left frame to
        segmentation, and counts the backend's odometry updates."""
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    def status(self) -> BridgeStatus:
        """The status reply for this drone's last pair."""
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    def counts(self, *, processing: bool) -> DroneCounts:
        """This session's counts; `processing` marks it the drone being processed now."""
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    def close(self) -> None:
        """Closes the backend and the segmentation run, and finishes the recorder."""
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")


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

    def handle(self, message: bytes) -> BridgeStatus:
        """One wire message in, its status reply out. A pair before any hello is a
        `BevyWireError`."""
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    def counts(self) -> tuple[DroneCounts, ...]:
        """Every drone session's counts, in drone-id order."""
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    def processing(self) -> str | None:
        """The drone whose frame was processed last; `None` before any."""
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    def close(self) -> None:
        """Finishes every drone session, in drone-id order, and unregisters the connection."""
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")


class SamSegmentationSink:
    """A `SegmentationSink` over the station's `SamDetector`: a worker thread runs the detector
    on each submitted left frame, `queue_size` frames waiting at most (a newer frame drops the
    oldest); counts frames segmented, detections and frames dropped. `close` lets the waiting
    frames finish, then stops the worker."""

    def __init__(self, detector: SamDetector, *, queue_size: int = SAM_QUEUE_SIZE) -> None:
        self._detector = detector
        self._queue_size = queue_size

    @property
    def segmented_frames(self) -> int:
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    @property
    def detections(self) -> int:
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    @property
    def dropped_frames(self) -> int:
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    def submit(self, left: RawFrame) -> None:
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    def close(self) -> None:
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")


class PerceptionRegistry:
    """The connected bridge pages, by the scenario their `hello` names; the latest page of a
    scenario wins."""

    def register(self, scenario_id: str, perception: FleetPerception) -> None:
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    def unregister(self, scenario_id: str, perception: FleetPerception) -> None:
        """Forgets `perception` if it is still the scenario's page."""
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")

    def perception(self, scenario_id: str) -> FleetPerception | None:
        """The scenario's connected page; `None` when no page streams it."""
        # TODO(pr-5): implement
        raise NotImplementedError("pr-5: implement")
