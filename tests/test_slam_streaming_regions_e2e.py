"""Real-container e2e: SAM regions answered with dense points (see test_slam_streaming_e2e)."""

import time
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.demo.datasets import scaled_sensor_yaml
from surmap.demo.server import rectified_to_raw
from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus
from surmap.slam.stream_protocol import OdomUpdate, Rectification
from surmap.slam.streaming import StreamingRtabmapBackend, pose_rotation
from surmap.types import Pose, StereoFramePair
from tests.test_slam_streaming_e2e import FIXTURE, _require_prepared

Box: TypeAlias = tuple[float, float, float, float]


def _feed_fixture(backend: StreamingRtabmapBackend, timestamps: list[object]) -> None:
    for index, t_ns in enumerate(timestamps):
        backend.process_frame(
            StereoFramePair(
                frame_id=index + 1,
                t_ns=int(str(t_ns)),
                left_ref=str(FIXTURE / "mav0" / "cam0" / "data" / f"{t_ns}.jpg"),
                right_ref=str(FIXTURE / "mav0" / "cam1" / "data" / f"{t_ns}.jpg"),
                calibration_id="euroc-v1-01-stream",
            )
        )
        backend.poll_updates()
        time.sleep(1 / 20)


def _in_camera(points: NDArray[np.float64], pose: Pose) -> NDArray[np.float64]:
    """Map-frame points into the (rectified, optical) camera frame of `pose`."""
    rotation = pose_rotation(pose).astype(np.float64)
    origin = np.array([pose.position.x, pose.position.y, pose.position.z])
    return np.asarray((points - origin) @ rotation, dtype=np.float64)


def _inside(pixels: NDArray[np.float64], box: Box) -> float:
    x0, y0, x1, y1 = box
    tolerance = 2.0
    inside = (
        (pixels[:, 0] >= x0 - tolerance)
        & (pixels[:, 0] <= x1 + tolerance)
        & (pixels[:, 1] >= y0 - tolerance)
        & (pixels[:, 1] <= y1 + tolerance)
    )
    return float(inside.mean())


def _box_polygon(box: Box) -> tuple[tuple[float, float], ...]:
    x0, y0, x1, y1 = box
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _xyz(result: RegionResult) -> NDArray[np.float64]:
    return np.array([(p.x, p.y, p.z) for p in result.points], dtype=np.float64).reshape(-1, 3)


CENTRE = (120.0, 70.0, 260.0, 170.0)
WHOLE = (20.0, 20.0, 356.0, 220.0)


@dataclass(frozen=True)
class LiveRegions:
    """The fixture streamed live once, and the regions asked of one recent frame."""

    odometry: OdomUpdate
    rectification: Rectification
    left: RegionResult
    left_whole: RegionResult
    right: RegionResult
    expired: RegionResult


@pytest.fixture(scope="module")
def live() -> LiveRegions:
    manifest = _require_prepared()
    timestamps = manifest["frame_timestamps_ns"]
    assert isinstance(timestamps, list)
    cam0 = (FIXTURE / "mav0" / "cam0" / "sensor.yaml").read_text(encoding="utf-8")
    cam1 = (FIXTURE / "mav0" / "cam1" / "sensor.yaml").read_text(encoding="utf-8")
    # Frames stay queryable for 2 s, so frame 1 has aged out by the end
    backend = StreamingRtabmapBackend(
        cam0_yaml=scaled_sensor_yaml(cam0, 376, 240),
        cam1_yaml=scaled_sensor_yaml(cam1, 376, 240),
        region_buffer_s=2.0,
    )
    target = len(timestamps) - 5
    try:
        _feed_fixture(backend, timestamps)
        deadline = time.monotonic() + 30
        while backend.frame_odometry(target) is None and time.monotonic() < deadline:
            backend.poll_updates()
            time.sleep(0.05)
        odometry = backend.frame_odometry(target)
        rectification = backend.rectification
        assert odometry is not None and odometry.map_pose is not None
        assert rectification is not None

        def ask(query_id: int, frame_id: int, channel: int, box: Box) -> RegionResult:
            query = RegionQuery(query_id, frame_id, channel, 376, 240, _box_polygon(box))
            return backend.region_points(query, timeout=10.0)

        return LiveRegions(
            odometry=odometry,
            rectification=rectification,
            left=ask(1, target, 0, CENTRE),
            left_whole=ask(2, target, 0, WHOLE),
            right=ask(3, target, 1, CENTRE),
            expired=ask(4, 1, 0, CENTRE),
        )
    finally:
        backend.close()


def test_a_sam_region_is_far_denser_than_rtabmaps_own_features(live: LiveRegions) -> None:
    # Given RTAB-Map's tracked features inside the centre box
    sparse = sum(
        1
        for k in live.odometry.keypoints
        if CENTRE[0] <= k.u <= CENTRE[2] and CENTRE[1] <= k.v <= CENTRE[3]
    )

    # When / Then the region's dense answer has thousands of points, 20x the features
    assert live.left.status is RegionStatus.OK
    assert len(live.left.points) > 2_000
    assert len(live.left.points) > 20 * max(1, sparse)


def test_a_sam_regions_points_project_back_inside_its_polygon(live: LiveRegions) -> None:
    # Given the left region's points in that frame's camera
    camera = _in_camera(_xyz(live.left), _map_pose(live.odometry))
    fx, fy, cx, cy = live.rectification.rectified

    # When they are projected back onto the raw image
    rectified = np.stack(
        [fx * camera[:, 0] / camera[:, 2] + cx, fy * camera[:, 1] / camera[:, 2] + cy], axis=1
    )

    # Then almost all land inside the box SAM drew
    assert _inside(rectified_to_raw(rectified, live.rectification), CENTRE) > 0.95


def test_a_right_channel_region_lies_on_the_surface_the_left_one_sees(live: LiveRegions) -> None:
    # Given the right-channel region and the whole left view of the same frame
    assert live.right.status is RegionStatus.OK
    right_points = _xyz(live.right)[:: max(1, len(live.right.points) // 500)]
    left_points = _xyz(live.left_whole)

    # When each right point is matched to its nearest left point
    nearest = np.min(
        np.linalg.norm(right_points[:, None, :] - left_points[None, :, :], axis=2), axis=1
    )

    # Then they agree to within centimetres
    assert float(np.median(nearest)) < 0.05


def test_a_frame_older_than_the_ring_is_reported_expired(live: LiveRegions) -> None:
    # Given / When frame 1 was asked after the 2 s ring moved past it
    # Then it is reported expired, with no points guessed
    assert live.expired.status is RegionStatus.FRAME_EXPIRED
    assert live.expired.points == ()


def _map_pose(odometry: OdomUpdate) -> Pose:
    assert odometry.map_pose is not None
    return odometry.map_pose
