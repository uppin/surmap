"""A solved stereo estimate as the EuRoC cam0/cam1 `sensor.yaml` pair.

Each eye keeps its own intrinsics and k1, k2, p1, p2 distortion, and
the two `T_BS` body poses encode the solved extrinsic: the streaming
sidecar (`deploy/rtabmap-stream`) recovers left-in-right as
inv(T_BS_cam1) · T_BS_cam0 and rectifies from it, as RTAB-Map's own
calibration rectifies from `stereoCalibrate`'s R and T. The body frame
and optical rotation match `surmap.simulation.calibration`: +X up,
+Y right, +Z forward, the left eye at Y = −baseline/2.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from surmap.calibration.port import LensModel, StereoEstimate

# Camera optical frame (+X right, +Y down, +Z forward) into the body frame.
_BODY_FROM_OPTICAL = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])


def _left_in_right(estimate: StereoEstimate) -> NDArray[np.float64]:
    pose = np.eye(4)
    pose[:3, :3] = np.array(estimate.rotation, dtype=np.float64).reshape(3, 3)
    pose[:3, 3] = estimate.translation_m
    return pose


def _yaml(
    t_bs: NDArray[np.float64],
    *,
    width: int,
    height: int,
    intrinsics: tuple[float, float, float, float],
    distortion: tuple[float, ...],
    rate_hz: float,
) -> str:
    rows = [", ".join(repr(float(v)) for v in row) for row in t_bs]
    return (
        "sensor_type: camera\n"
        "T_BS:\n"
        "  cols: 4\n"
        "  rows: 4\n"
        f"  data: [{rows[0]},\n"
        f"         {rows[1]},\n"
        f"         {rows[2]},\n"
        f"         {rows[3]}]\n"
        f"rate_hz: {rate_hz}\n"
        f"resolution: [{width}, {height}]\n"
        "camera_model: pinhole\n"
        f"intrinsics: [{', '.join(repr(float(v)) for v in intrinsics)}]\n"
        "distortion_model: radial-tangential\n"
        f"distortion_coefficients: [{', '.join(repr(float(v)) for v in distortion)}]\n"
    )


def estimated_sensor_yamls(
    estimate: StereoEstimate, *, width: int, height: int, rate_hz: float = 20.0
) -> tuple[str, str]:
    """EuRoC `sensor.yaml` text for cam0 (left) and cam1 (right).

    Radial-tangential only: the streaming sidecar rectifies, maps keypoints
    to raw pixels and answers regions with that model, so a rational or
    fisheye estimate would be misread rather than used.
    """
    if estimate.lens is not LensModel.PINHOLE_RADTAN:
        raise ValueError(
            f"{estimate.lens.value} estimates cannot be exported: the streaming sidecar "
            "takes radial-tangential (pinhole_radtan) calibrations only"
        )
    t_bs_left = np.eye(4)
    t_bs_left[:3, :3] = _BODY_FROM_OPTICAL
    t_bs_left[:3, 3] = (0.0, -estimate.baseline_m / 2, 0.0)
    t_bs_right = t_bs_left @ np.linalg.inv(_left_in_right(estimate))
    left = _yaml(
        t_bs_left,
        width=width,
        height=height,
        intrinsics=(estimate.left_fx, estimate.left_fy, estimate.left_cx, estimate.left_cy),
        distortion=estimate.distortion_left,
        rate_hz=rate_hz,
    )
    right = _yaml(
        t_bs_right,
        width=width,
        height=height,
        intrinsics=(estimate.right_fx, estimate.right_fy, estimate.right_cx, estimate.right_cy),
        distortion=estimate.distortion_right,
        rate_hz=rate_hz,
    )
    return left, right
