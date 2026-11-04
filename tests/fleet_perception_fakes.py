"""The station's per-drone perception under test: Bevy wire messages from a fleet page, and fakes
at the router's seams — one `FakeBackend` per drone map the factory builds, one `RecordingSink`
per drone's segmentation run, one `FakeRecorder` per drone's capture — all writing to one shared
event log, so a test can see what happened to which drone, and in what order.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from surmap.simulation.bevy_wire import BevyPair, BridgeStatus
from surmap.simulation.fleet.perception import FleetPerception, PerceptionRegistry
from surmap.slam.stream_protocol import OdomUpdate
from surmap.survey.sam import RawFrame
from surmap.types import Pose, StereoFramePair, Vec3

GOLDENS = Path(__file__).parent / "fixtures" / "bevy_sim_wire"
HELLO = (GOLDENS / "hello.bin").read_bytes()
PAIR = (GOLDENS / "pair.bin").read_bytes()
PAIR_DRONE = (GOLDENS / "pair-drone.bin").read_bytes()

SCENARIO = "quake-fleet"
SW_D1 = "nest-sw-d1"
SW_D2 = "nest-sw-d2"
NE_D1 = "nest-ne-d1"
NE_D2 = "nest-ne-d2"
ROOF_D1 = "nest-roof-d1"
# The 4x2 frame every fake pair carries.
WIDTH, HEIGHT = 4, 2
LEFT = bytes(range(8))
RIGHT = bytes(range(8, 16))
FRAME_PERIOD_NS = 100_000_000


def framed(header: dict[str, object], payload: bytes = b"") -> bytes:
    """A wire message: `u32` LE header length, compact JSON header, payload."""
    text = json.dumps(header, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(text)) + text + payload


def the_golden_hello_header() -> dict[str, object]:
    (length,) = struct.unpack_from("<I", HELLO, 0)
    header: dict[str, object] = json.loads(HELLO[4 : 4 + length])
    return header


def a_hello(scenario: str | None = SCENARIO, camera: object | None = None) -> bytes:
    """The golden hello (its camera unless `camera` is given), naming `scenario`."""
    header = the_golden_hello_header()
    if camera is not None:
        header["camera"] = camera
    if scenario is not None:
        header["scenario"] = scenario
    return framed(header)


def a_pair(
    frame_id: int,
    drone: str | None,
    *,
    left: bytes = LEFT,
    right: bytes = RIGHT,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> bytes:
    """A pair from `drone`'s eyes (none: a single-drone page), at `frame_id` × 100 ms."""
    header: dict[str, object] = {
        "type": "pair",
        "frame_id": frame_id,
        "t_ns": frame_id * FRAME_PERIOD_NS,
        "width": width,
        "height": height,
        "encoding": "gray8",
        "pose_enu": [1.0, 3.0, 2.0, 0.0, 0.0, 0.0, 1.0],
    }
    if drone is not None:
        header["drone_id"] = drone
    return framed(header, left + right)


def blocks(*runs: tuple[str | None, int]) -> list[bytes]:
    """Consecutive pairs, frame ids from 1: `(drone, n)` is that drone's next n frames — the
    active drone switching between blocks."""
    messages: list[bytes] = []
    for drone, count in runs:
        start = len(messages) + 1
        messages.extend(a_pair(start + i, drone) for i in range(count))
    return messages


def a_posed_update(frame_id: int) -> OdomUpdate:
    return OdomUpdate(
        frame_id=frame_id,
        t_ns=frame_id * FRAME_PERIOD_NS,
        pose=Pose(Vec3(1.0, 3.0, 2.0), (0.0, 0.0, 0.0, 1.0)),
        lost=False,
        ms=1.0,
    )


class FakeBackend:
    """One drone's map: records its frames, poses every one, one keyframe per frame."""

    def __init__(self, events: list[str]) -> None:
        self.frames: list[StereoFramePair] = []
        self.closed = False
        self._events = events
        self._updates: list[OdomUpdate] = []

    @property
    def keyframe_count(self) -> int:
        return len(self.frames)

    @property
    def dropped_frames(self) -> int:
        return 0

    @property
    def frame_ids(self) -> list[int]:
        return [frame.frame_id for frame in self.frames]

    def process_frame(self, frame: StereoFramePair) -> None:
        self.frames.append(frame)
        self._updates.append(a_posed_update(frame.frame_id))

    def poll_updates(self) -> list[OdomUpdate]:
        updates, self._updates = self._updates, []
        return updates

    def close(self) -> None:
        self.closed = True
        self._events.append(f"backend closed after frame {self.frame_ids[-1]}")


class RecordingBackends:
    """The backend factory: a new `FakeBackend` per call, remembering the calibration."""

    def __init__(self, events: list[str]) -> None:
        self.built: list[FakeBackend] = []
        self.calibrations: list[tuple[int, int]] = []
        self._events = events

    def __call__(self, *, cam0_yaml: str, cam1_yaml: str, width: int, height: int) -> FakeBackend:
        backend = FakeBackend(self._events)
        self.built.append(backend)
        self.calibrations.append((width, height))
        return backend

    def of_frame(self, frame_id: int) -> FakeBackend:
        """The one map that received `frame_id`."""
        (backend,) = [b for b in self.built if frame_id in b.frame_ids]
        return backend


class RecordingSink:
    """One drone's segmentation run: records its left frames, two detections each."""

    def __init__(self, drone: str, events: list[str]) -> None:
        self.drone = drone
        self.frames: list[RawFrame] = []
        self.closed = False
        self._events = events

    @property
    def segmented_frames(self) -> int:
        return len(self.frames)

    @property
    def detections(self) -> int:
        return 2 * len(self.frames)

    def submit(self, left: RawFrame) -> None:
        self.frames.append(left)

    def close(self) -> None:
        self.closed = True
        self._events.append(f"segmentation of {self.drone} closed")


@dataclass
class RecordingSinks:
    events: list[str]
    by_drone: dict[str, RecordingSink] = field(default_factory=dict)

    def __call__(self, drone: str) -> RecordingSink:
        sink = RecordingSink(drone, self.events)
        self.by_drone[drone] = sink
        return sink

    def seen(self) -> dict[str, list[tuple[int, int, bytes]]]:
        """Each drone's segmented frames: frame id, camera channel, image bytes."""
        return {
            drone: [(f.frame_id, f.channel, f.data) for f in sink.frames]
            for drone, sink in self.by_drone.items()
        }


class FakeRecorder:
    """One drone's capture: records its pairs until finished."""

    def __init__(self, drone: str, events: list[str]) -> None:
        self.drone = drone
        self.pairs: list[BevyPair] = []
        self.finished = False
        self._events = events

    def record_pair(self, pair: BevyPair) -> None:
        self.pairs.append(pair)

    def finish(self) -> None:
        self.finished = True
        self._events.append(f"capture of {self.drone} finished")


@dataclass
class RecordingRecorders:
    events: list[str]
    by_drone: dict[str, FakeRecorder] = field(default_factory=dict)

    def __call__(self, drone: str) -> FakeRecorder:
        recorder = FakeRecorder(drone, self.events)
        self.by_drone[drone] = recorder
        return recorder

    def recorded(self) -> dict[str, list[int]]:
        """Each drone's captured frame ids."""
        return {
            drone: [pair.frame_id for pair in recorder.pairs]
            for drone, recorder in self.by_drone.items()
        }


@dataclass
class PerceptionRig:
    """A page connection's `FleetPerception` over the fakes, and what they saw."""

    perception: FleetPerception
    backends: RecordingBackends
    sinks: RecordingSinks
    recorders: RecordingRecorders
    registry: PerceptionRegistry
    events: list[str]

    def streams(self, *messages: bytes) -> list[BridgeStatus]:
        """The page sends `messages` in order; the status reply of each."""
        return [self.perception.handle(message) for message in messages]

    def opened(self, scenario: str | None = SCENARIO) -> PerceptionRig:
        """The page has sent its hello."""
        self.perception.handle(a_hello(scenario))
        return self


def a_perception(registry: PerceptionRegistry | None = None) -> PerceptionRig:
    """A connection with nothing received yet, recording every drone's capture."""
    events: list[str] = []
    backends = RecordingBackends(events)
    sinks = RecordingSinks(events)
    recorders = RecordingRecorders(events)
    shared = registry if registry is not None else PerceptionRegistry()
    perception = FleetPerception(backends, sinks, registry=shared, recorder_factory=recorders)
    return PerceptionRig(perception, backends, sinks, recorders, shared, events)


def an_open_perception(registry: PerceptionRegistry | None = None) -> PerceptionRig:
    """A connection whose page has sent its hello for `quake-fleet`."""
    return a_perception(registry).opened()
