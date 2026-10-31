"""Real-container e2e: SAM regions answered with dense points (see test_slam_streaming_e2e)."""

import time

import numpy as np
from numpy.typing import NDArray

from surmap.demo.datasets import scaled_sensor_yaml
from surmap.demo.server import rectified_to_raw
from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus
from surmap.slam.streaming import StreamingRtabmapBackend, pose_rotation
from surmap.types import Pose, StereoFramePair
from tests.test_slam_streaming_e2e import FIXTURE, _require_prepared


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


def _inside(pixels: NDArray[np.float64], box: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = box
    tolerance = 2.0
    inside = (
        (pixels[:, 0] >= x0 - tolerance)
        & (pixels[:, 0] <= x1 + tolerance)
        & (pixels[:, 1] >= y0 - tolerance)
        & (pixels[:, 1] <= y1 + tolerance)
    )
    return float(inside.mean())


def _box_polygon(box: tuple[float, float, float, float]) -> tuple[tuple[float, float], ...]:
    x0, y0, x1, y1 = box
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _xyz(result: RegionResult) -> NDArray[np.float64]:
    return np.array([(p.x, p.y, p.z) for p in result.points], dtype=np.float64).reshape(-1, 3)


def test_a_sam_region_is_answered_with_dense_points_on_both_channels() -> None:
    manifest = _require_prepared()
    timestamps = manifest["frame_timestamps_ns"]
    assert isinstance(timestamps, list)
    cam0 = (FIXTURE / "mav0" / "cam0" / "sensor.yaml").read_text(encoding="utf-8")
    cam1 = (FIXTURE / "mav0" / "cam1" / "sensor.yaml").read_text(encoding="utf-8")
    # Given the fixture streamed live, with frames queryable for 2 s
    backend = StreamingRtabmapBackend(
        cam0_yaml=scaled_sensor_yaml(cam0, 376, 240),
        cam1_yaml=scaled_sensor_yaml(cam1, 376, 240),
        region_buffer_s=2.0,
    )
    target = len(timestamps) - 5
    centre = (120.0, 70.0, 260.0, 170.0)
    whole = (20.0, 20.0, 356.0, 220.0)
    try:
        _feed_fixture(backend, timestamps)
        deadline = time.monotonic() + 30
        while backend.frame_odometry(target) is None and time.monotonic() < deadline:
            backend.poll_updates()
            time.sleep(0.05)
        odometry = backend.frame_odometry(target)
        rectification = backend.rectification

        # When SAM's centre box on the left image of that frame is queried,
        # and the same frame's right image, and a frame long gone
        left = backend.region_points(
            RegionQuery(1, target, 0, 376, 240, _box_polygon(centre)), timeout=10.0
        )
        left_whole = backend.region_points(
            RegionQuery(2, target, 0, 376, 240, _box_polygon(whole)), timeout=10.0
        )
        right = backend.region_points(
            RegionQuery(3, target, 1, 376, 240, _box_polygon(centre)), timeout=10.0
        )
        expired = backend.region_points(
            RegionQuery(4, 1, 0, 376, 240, _box_polygon(centre)), timeout=10.0
        )
    finally:
        backend.close()

    assert odometry is not None and odometry.map_pose is not None and rectification is not None
    assert left.status is RegionStatus.OK and right.status is RegionStatus.OK
    assert expired.status is RegionStatus.FRAME_EXPIRED and expired.points == ()

    # Then the region is dense: far more points than RTAB-Map's own features in it
    sparse = sum(
        1
        for k in odometry.keypoints
        if centre[0] <= k.u <= centre[2] and centre[1] <= k.v <= centre[3]
    )
    assert len(left.points) > 2_000
    assert len(left.points) > 20 * max(1, sparse)

    # And every point projects back inside the polygon SAM drew on the raw image
    camera = _in_camera(_xyz(left), odometry.map_pose)
    fx, fy, cx, cy = rectification.rectified
    rectified = np.stack(
        [fx * camera[:, 0] / camera[:, 2] + cx, fy * camera[:, 1] / camera[:, 2] + cy], axis=1
    )
    assert _inside(rectified_to_raw(rectified, rectification), centre) > 0.95

    # And the right channel's region lies on the same surface the left one sees
    right_points = _xyz(right)[:: max(1, len(right.points) // 500)]
    left_points = _xyz(left_whole)
    nearest = np.min(
        np.linalg.norm(right_points[:, None, :] - left_points[None, :, :], axis=2), axis=1
    )
    assert float(np.median(nearest)) < 0.05
