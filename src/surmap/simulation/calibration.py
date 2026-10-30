"""Stereo calibration → EuRoC `sensor.yaml` text."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StereoCalibrationSpec:
    """Intrinsics + baseline for a Gazebo/PX4 (or real) stereo rig."""

    calibration_id: str
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    baseline_m: float
    rate_hz: float = 20.0


def render_cam_sensor_yaml(spec: StereoCalibrationSpec, channel: int) -> str:
    """EuRoC-style camera `sensor.yaml` for cam0 (left) or cam1 (right).

    `T_BS` is in the EuRoC body frame (+X up, +Y right, +Z forward), the
    frame `rtabmap-euroc_dataset` and the demo fixture use. The left eye
    is therefore at Y = −baseline/2. Gazebo's model keeps that same eye
    at Y = +baseline/2 because a Gazebo link is forward-left-up; the
    export negates Y rather than moving the simulated camera.

    The rotation takes the camera optical frame (+X right, +Y down,
    +Z forward) into that body frame — the same rotation real EuRoC
    `cam0` uses, which the dataset tool already converts with
    `opticalRotation()`. An identity block would roll the image by 90°.
    """
    if channel not in (0, 1):
        raise ValueError(f"channel must be 0 or 1, got {channel}")
    half = spec.baseline_m / 2.0
    y = -half if channel == 0 else half
    return (
        "sensor_type: camera\n"
        "T_BS:\n"
        "  cols: 4\n"
        "  rows: 4\n"
        "  data: [0.0, -1.0, 0.0, 0.0,\n"
        f"         1.0, 0.0, 0.0, {y},\n"
        "         0.0, 0.0, 1.0, 0.0,\n"
        "         0.0, 0.0, 0.0, 1.0]\n"
        f"rate_hz: {spec.rate_hz}\n"
        f"resolution: [{spec.width}, {spec.height}]\n"
        "camera_model: pinhole\n"
        f"intrinsics: [{spec.fx}, {spec.fy}, {spec.cx}, {spec.cy}]\n"
        "distortion_model: radial-tangential\n"
        "distortion_coefficients: [0.0, 0.0, 0.0, 0.0]\n"
    )
