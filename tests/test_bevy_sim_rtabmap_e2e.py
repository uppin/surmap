"""Acceptance: Bevy captures streamed through the real RTAB-Map sidecar.

The simulation is a perfect world — exact intrinsics, zero distortion,
known poses and object boxes — so RTAB-Map is judged against the truth
directly: frames are fed in lockstep (every frame is processed, none is
dropped), the map is anchored to ENU once from the first frame's camera
pose and never re-fitted, and dense points are judged in the camera
frame against the true surfaces, in units of the disparity error the
rig's baseline allows (one pixel of disparity is z²/(f·B) metres).

Mirrors tests/test_slam_streaming_e2e.py's docker/image skip; the
captures are committed, so a missing capture fails, and
SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1 (CI) turns the image skip into a failure.
"""

import os
import pathlib
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.simulation.bevy_capture import BevyCapture, CapturedFrame, load_bevy_capture
from surmap.simulation.bevy_ground_truth import (
    box_surface_distance,
    left_eye_optical_pose,
    project_box,
)
from surmap.simulation.bevy_wire import GroundTruthBox
from surmap.simulation.camera_profile import CameraProfile, profile_sensor_yaml
from surmap.simulation.slam_eval import anchor_map_to_enu, in_camera_frame, track_drift
from surmap.simulation.trajectory_eval import RigidAlignment
from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus
from surmap.slam.stream_protocol import OdomUpdate
from surmap.slam.streaming import StreamingRtabmapBackend, stream_image_tag
from surmap.types import Pose

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
BLOCK = FIXTURES / "bevy_sim_capture"
REQUIRED = os.environ.get("SURMAP_REQUIRE_RTABMAP_STREAM_E2E") == "1"
FRAME_TIMEOUT_S = 15.0
# A centred 40 px square: answered only to learn the frame's camera pose.
CENTRE_SQUARE = ((300.0, 220.0), (340.0, 220.0), (340.0, 260.0), (300.0, 260.0))

Points = NDArray[np.float64]


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


def _position(pose: Pose) -> Points:
    return np.array([pose.position.x, pose.position.y, pose.position.z], dtype=np.float64)


def _rotation(pose: Pose) -> Points:
    x, y, z, w = pose.orientation_xyzw
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


@dataclass
class StreamedRun:
    """One capture streamed in lockstep, anchored to ENU at its first frame."""

    capture: BevyCapture
    profile: CameraProfile
    odometry: dict[int, OdomUpdate]
    dropped: int
    anchor: RigidAlignment
    base_to_camera: Points
    keyframes: int
    map_points: int
    region: RegionResult
    region_frame: CapturedFrame
    region_object: GroundTruthBox

    def posed(self) -> list[CapturedFrame]:
        return [
            f
            for f in self.capture.frames
            if (u := self.odometry.get(f.pair.frame_id)) is not None
            and u.pose is not None
            and not u.lost
        ]

    def camera_track(self, frames: list[CapturedFrame]) -> Points:
        """RTAB-Map's left camera positions (map frame) for `frames`, from odometry."""
        rows = []
        for f in frames:
            pose = self.odometry[f.pair.frame_id].pose
            assert pose is not None
            rows.append(_position(pose) + _rotation(pose) @ self.base_to_camera)
        return np.array(rows)

    def true_track(self, frames: list[CapturedFrame]) -> Points:
        cal = self.capture.calibration
        return np.array([_position(left_eye_optical_pose(f.pose_enu, cal)) for f in frames])


def _polygon_area(polygon: tuple[tuple[float, float], ...]) -> float:
    xs = np.array([p[0] for p in polygon])
    ys = np.array([p[1] for p in polygon])
    return float(0.5 * abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1))))


def _nearest_framed_object(
    run_capture: BevyCapture, frame: CapturedFrame
) -> tuple[GroundTruthBox, tuple[tuple[float, float], ...]] | None:
    """The nearest ground-truth object whose whole outline is in the image."""
    cal = run_capture.calibration
    rig = _position(frame.pose_enu)
    best: tuple[float, GroundTruthBox, tuple[tuple[float, float], ...]] | None = None
    for obj in run_capture.objects:
        polygon = project_box(obj, frame.pose_enu, cal)
        inside = all(0 <= x < cal.width and 0 <= y < cal.height for x, y in polygon)
        if len(polygon) < 3 or not inside or _polygon_area(polygon) < 2000.0:
            continue
        centre = np.array(
            [(obj.min_enu.x + obj.max_enu.x) / 2, (obj.min_enu.y + obj.max_enu.y) / 2, 0.0]
        )
        distance = float(np.linalg.norm(centre[:2] - rig[:2]))
        if best is None or distance < best[0]:
            best = (distance, obj, polygon)
    return None if best is None else (best[1], best[2])


def _stream(capture_dir: pathlib.Path) -> Iterator[StreamedRun]:
    _require_prepared(capture_dir)
    capture = load_bevy_capture(capture_dir)
    profile = capture.camera
    assert profile is not None, "the capture must carry the camera profile it was rendered with"
    cal = capture.calibration
    backend = StreamingRtabmapBackend(
        cam0_yaml=profile_sensor_yaml(profile, 0),
        cam1_yaml=profile_sensor_yaml(profile, 1),
        width=profile.width,
        height=profile.height,
        region_buffer_s=1e6,
        dense_journal=True,
    )
    odometry: dict[int, OdomUpdate] = {}

    def drain() -> None:
        for update in backend.poll_updates():
            if isinstance(update, OdomUpdate):
                odometry[update.frame_id] = update

    try:
        anchor: RigidAlignment | None = None
        base_to_camera = np.zeros(3)
        for frame in capture.frames:
            backend.process_frame(frame.pair)
            deadline = time.monotonic() + FRAME_TIMEOUT_S
            while frame.pair.frame_id not in odometry and time.monotonic() < deadline:
                time.sleep(0.01)
                drain()
            update = odometry.get(frame.pair.frame_id)
            if anchor is None and update is not None and update.pose is not None:
                centre = backend.region_points(
                    RegionQuery(1, frame.pair.frame_id, 0, cal.width, cal.height, CENTRE_SQUARE),
                    timeout=30,
                )
                assert centre.camera is not None
                anchor = anchor_map_to_enu(
                    centre.camera, left_eye_optical_pose(frame.pose_enu, cal)
                )
                base_to_camera = _rotation(update.pose).T @ (
                    _position(centre.camera) - _position(update.pose)
                )
        assert anchor is not None, "no frame was ever posed"
        posed = [f for f in capture.frames if (u := odometry.get(f.pair.frame_id)) and u.pose]
        region_frame = posed[-1]
        framed = _nearest_framed_object(capture, region_frame)
        assert framed is not None, "the capture must end with a ground-truth object in view"
        region_object, polygon = framed
        region = backend.region_points(
            RegionQuery(2, region_frame.pair.frame_id, 0, cal.width, cal.height, polygon),
            timeout=30,
        )
        backend.flush()
        yield StreamedRun(
            capture=capture,
            profile=profile,
            odometry=odometry,
            dropped=backend.dropped_frames,
            anchor=anchor,
            base_to_camera=base_to_camera,
            keyframes=backend.keyframe_count,
            map_points=len(backend.map_snapshot()),
            region=region,
            region_frame=region_frame,
            region_object=region_object,
        )
    finally:
        backend.close()


@pytest.fixture(scope="module")
def block() -> Iterator[StreamedRun]:
    yield from _stream(BLOCK)


def test_every_frame_of_the_block_leg_is_tracked(block: StreamedRun) -> None:
    # Given the 9 s block leg streamed frame by frame (module fixture)
    total = len(block.capture.frames)

    # When the posed frames are counted
    posed = len(block.posed())

    # Then none was dropped or lost, and RTAB-Map built a map
    assert (posed, block.dropped) == (total, 0)
    assert block.keyframes >= 3
    assert block.map_points >= 2000


def test_odometry_drifts_less_than_four_percent_of_the_leg(block: StreamedRun) -> None:
    # Given the leg anchored to the truth at its first frame and never re-fitted
    frames = block.posed()
    truth = block.true_track(frames)
    leg = float(np.linalg.norm(np.diff(truth, axis=0), axis=1).sum())

    # When the odometry track is compared with the truth through that anchor
    drift = track_drift(block.camera_track(frames), truth, block.anchor)

    # Then the end is within 4 % of the distance flown
    assert drift[-1] <= 0.04 * leg, f"{drift[-1]:.2f} m after {leg:.1f} m"


def test_dense_points_on_an_object_lie_on_its_true_surface(block: StreamedRun) -> None:
    # Given the region answer for the nearest fully framed ground-truth object
    result, frame, box = block.region, block.region_frame, block.region_object
    assert result.status is RegionStatus.OK and result.camera is not None
    true_camera = left_eye_optical_pose(frame.pose_enu, block.capture.calibration)

    # When its points are taken into the camera frame and placed with the true camera pose
    local = in_camera_frame(
        np.array([[p.x, p.y, p.z] for p in result.points], dtype=np.float64), result.camera
    )
    in_enu = local @ _rotation(true_camera).T + _position(true_camera)
    distance = box_surface_distance(in_enu, box)
    depth = float(np.median(local[:, 2]))
    metres_per_pixel = depth**2 / (block.profile.fx * block.profile.baseline_m)

    # Then they sit on the object within a quarter pixel of disparity at their depth
    assert len(result.points) >= 200
    assert float(np.median(distance)) <= 0.25 * metres_per_pixel, (
        f"median {np.median(distance):.2f} m at {depth:.1f} m ({metres_per_pixel:.2f} m/px)"
    )
