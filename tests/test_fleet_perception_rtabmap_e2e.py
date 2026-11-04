"""Acceptance: two drones' streams, each mapped by its own real RTAB-Map sidecar.

The committed Bevy capture (`tests/fixtures/bevy_sim_capture`) is streamed through one
`FleetPerception` as the wire messages a fleet page sends while the agent switches the active
drone: frames 1-30 as nest-sw-d1, 31-60 as nest-ne-d1, 61-90 as nest-sw-d1 again. Each drone's
map is a real `StreamingRtabmapBackend`, fed in lockstep (each frame waits for its odometry, so
none is dropped). Both maps must gain keyframes, and nest-sw-d1's frames after the switch back
must continue in the map it started — visual odometry resets across the gap, so RTAB-Map starts
a new piece of that map, which this capture is too short to see joined.

Mirrors tests/test_bevy_sim_rtabmap_e2e.py's docker/image skip; the capture is committed, so a
missing capture fails, and SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1 (CI) turns the image skip into a
failure.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from PIL import Image

from surmap.simulation.bevy_capture import BevyCapture, CapturedFrame, load_bevy_capture
from surmap.simulation.fleet.perception import DroneCounts, FleetPerception
from surmap.slam.stream_protocol import OdomUpdate, Rectification
from surmap.slam.streaming import StreamingRtabmapBackend, stream_image_tag
from surmap.types import StereoFramePair
from tests.fleet_perception_fakes import (
    NE_D1,
    SCENARIO,
    SW_D1,
    RecordingSinks,
    a_hello,
    framed,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CAPTURE = FIXTURES / "bevy_sim_capture"
REQUIRED = os.environ.get("SURMAP_REQUIRE_RTABMAP_STREAM_E2E") == "1"
FRAME_TIMEOUT_S = 15.0
# The active drone, block by block: (drone, first frame id, last frame id).
SWITCHES = ((SW_D1, 1, 30), (NE_D1, 31, 60), (SW_D1, 61, 90))


def _require_prepared(capture_dir: pathlib.Path) -> None:
    if not (capture_dir / "frames.jsonl").is_file():
        pytest.fail(f"committed Bevy capture is missing: {capture_dir}")
    tag = stream_image_tag()
    docker = shutil.which("docker")
    image_ready = False
    if docker is not None:
        image = subprocess.run([docker, "image", "inspect", tag], capture_output=True, text=True)
        image_ready = image.returncode == 0
    if docker is None or not image_ready:
        message = "streaming e2e not prepared: run `uv run python scripts/build_rtabmap_stream.py`"
        if REQUIRED:
            pytest.fail(message)
        pytest.skip(message)


class LockstepBackend:
    """A real streaming backend whose `process_frame` returns once the frame's odometry is out,
    so every frame is processed; the updates it waited for are handed on by `poll_updates`."""

    def __init__(self, inner: StreamingRtabmapBackend) -> None:
        self.inner = inner
        self._held: list[OdomUpdate] = []

    @property
    def keyframe_count(self) -> int:
        return self.inner.keyframe_count

    @property
    def dropped_frames(self) -> int:
        return self.inner.dropped_frames

    @property
    def rectification(self) -> Rectification | None:
        return self.inner.rectification

    def process_frame(self, frame: StereoFramePair) -> None:
        self.inner.process_frame(frame)
        deadline = time.monotonic() + FRAME_TIMEOUT_S
        while not self._answered(frame.frame_id) and time.monotonic() < deadline:
            time.sleep(0.01)
            self._held.extend(u for u in self.inner.poll_updates() if isinstance(u, OdomUpdate))

    def _answered(self, frame_id: int) -> bool:
        return any(update.frame_id == frame_id for update in self._held)

    def poll_updates(self) -> list[OdomUpdate]:
        self._held.extend(u for u in self.inner.poll_updates() if isinstance(u, OdomUpdate))
        updates, self._held = self._held, []
        return updates

    def close(self) -> None:
        self.inner.close()


class RealMaps:
    """The backend factory: one real sidecar per drone map, remembered in build order."""

    def __init__(self) -> None:
        self.built: list[LockstepBackend] = []

    def __call__(
        self, *, cam0_yaml: str, cam1_yaml: str, width: int, height: int
    ) -> LockstepBackend:
        backend = LockstepBackend(
            StreamingRtabmapBackend(
                cam0_yaml=cam0_yaml, cam1_yaml=cam1_yaml, width=width, height=height
            )
        )
        self.built.append(backend)
        return backend


def _grey(path: str) -> bytes:
    with Image.open(path) as image:
        return image.convert("L").tobytes()


def _pair_message(frame: CapturedFrame, drone: str, width: int, height: int) -> bytes:
    """The wire pair a fleet page sends for one captured frame of `drone`."""
    pose = frame.pose_enu
    header: dict[str, object] = {
        "type": "pair",
        "frame_id": frame.pair.frame_id,
        "t_ns": frame.pair.t_ns,
        "width": width,
        "height": height,
        "encoding": "gray8",
        "pose_enu": [pose.position.x, pose.position.y, pose.position.z, *pose.orientation_xyzw],
        "drone_id": drone,
    }
    return framed(header, _grey(frame.pair.left_ref) + _grey(frame.pair.right_ref))


def _drone_of(frame_id: int) -> str:
    (drone,) = [d for d, first, last in SWITCHES if first <= frame_id <= last]
    return drone


@dataclass
class TwoDroneRun:
    """The capture streamed as two drones, and each map's state at the switches."""

    capture: BevyCapture
    maps_built: int
    at_first_switch: DroneCounts
    at_the_end: dict[str, DroneCounts]


def _stream_as_two_drones(capture_dir: pathlib.Path) -> Iterator[TwoDroneRun]:
    _require_prepared(capture_dir)
    capture = load_bevy_capture(capture_dir)
    profile = json.loads((capture_dir / "camera.json").read_text(encoding="utf-8"))
    width, height = int(profile["width"]), int(profile["height"])
    maps = RealMaps()
    perception = FleetPerception(maps, RecordingSinks([]))
    try:
        perception.handle(a_hello(SCENARIO, camera=profile))
        at_first_switch: DroneCounts | None = None
        for frame in capture.frames:
            drone = _drone_of(frame.pair.frame_id)
            perception.handle(_pair_message(frame, drone, width, height))
            if frame.pair.frame_id == SWITCHES[0][2]:
                (at_first_switch,) = perception.counts()
        assert at_first_switch is not None, "the capture must reach the first switch"
        yield TwoDroneRun(
            capture=capture,
            maps_built=len(maps.built),
            at_first_switch=at_first_switch,
            at_the_end={c.drone_id: c for c in perception.counts()},
        )
    finally:
        perception.close()


@pytest.fixture(scope="module")
def two_drones() -> Iterator[TwoDroneRun]:
    yield from _stream_as_two_drones(CAPTURE)


def test_two_real_rtabmap_sessions_both_map_and_one_resumes(two_drones: TwoDroneRun) -> None:
    # Given the capture streamed as nest-sw-d1, nest-ne-d1, then nest-sw-d1 again (fixture)
    # When each drone's map is read at the end
    sw, ne = two_drones.at_the_end[SW_D1], two_drones.at_the_end[NE_D1]

    # Then only two maps were built: nest-sw-d1's frames after the switch back continued the map
    # it started, which kept the keyframes it had at the switch, and nest-ne-d1's map grew too
    assert (two_drones.maps_built, sw.frames, ne.frames) == (2, 60, 30)
    assert sw.keyframes >= two_drones.at_first_switch.keyframes >= 1
    assert ne.keyframes >= 1
