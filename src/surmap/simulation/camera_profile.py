"""The Bevy simulation's stereo camera profile (`*.camera.json`).

One file describes the rig for both sides: the simulation renders its
eyes from it (`examples/bevy-sitl-poc/src/calibration.rs`), and RTAB-Map's
EuRoC `sensor.yaml` is derived from it here, so the rendered images and
the SLAM calibration cannot disagree. A pinhole profile yields exactly
what `render_cam_sensor_yaml` writes for the same numbers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from surmap.simulation.calibration import StereoCalibrationSpec, render_cam_sensor_yaml

LensModel = Literal["pinhole", "fisheye_equidistant"]
_MODELS: tuple[LensModel, ...] = ("pinhole", "fisheye_equidistant")


@dataclass(frozen=True)
class Mount:
    """Where the rig sits on the drone: offsets (m) and pitch below the horizon (deg)."""

    forward_m: float
    up_m: float
    pitch_deg: float


@dataclass(frozen=True)
class CameraProfile:
    id: str
    model: LensModel
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    distortion: tuple[float, float, float, float]
    baseline_m: float
    rate_hz: float
    mount: Mount

    def calibration_spec(self) -> StereoCalibrationSpec:
        return StereoCalibrationSpec(
            calibration_id=self.id,
            width=self.width,
            height=self.height,
            fx=self.fx,
            fy=self.fy,
            cx=self.cx,
            cy=self.cy,
            baseline_m=self.baseline_m,
            rate_hz=self.rate_hz,
        )


def _obj(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be a JSON object")
    return {str(k): v for k, v in value.items()}


def _number(obj: dict[str, object], key: str) -> float:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"camera profile field {key!r} must be a number")
    return float(value)


def _model(value: object) -> LensModel:
    for model in _MODELS:
        if value == model:
            return model
    raise ValueError(f"camera profile model must be one of {_MODELS}, got {value!r}")


def parse_camera_profile(raw: object) -> CameraProfile:
    obj = _obj(raw, "camera profile")
    profile_id = obj.get("id")
    if not isinstance(profile_id, str):
        raise ValueError("camera profile id must be a string")
    raw_distortion = obj.get("distortion", [0.0, 0.0, 0.0, 0.0])
    if not isinstance(raw_distortion, list) or len(raw_distortion) != 4:
        raise ValueError("camera profile distortion must be four numbers")
    k = tuple(_number({"k": item}, "k") for item in raw_distortion)
    mount = _obj(obj.get("mount"), "camera profile mount")
    profile = CameraProfile(
        id=profile_id,
        model=_model(obj.get("model")),
        width=int(_number(obj, "width")),
        height=int(_number(obj, "height")),
        fx=_number(obj, "fx"),
        fy=_number(obj, "fy"),
        cx=_number(obj, "cx"),
        cy=_number(obj, "cy"),
        distortion=(k[0], k[1], k[2], k[3]),
        baseline_m=_number(obj, "baseline_m"),
        rate_hz=_number(obj, "rate_hz"),
        mount=Mount(
            forward_m=_number(mount, "forward_m"),
            up_m=_number(mount, "up_m"),
            pitch_deg=_number(mount, "pitch_deg"),
        ),
    )
    if profile.model == "pinhole" and profile.distortion != (0.0, 0.0, 0.0, 0.0):
        raise ValueError(f"{profile.id}: a pinhole profile has no distortion")
    if min(profile.width, profile.height) <= 0 or min(profile.fx, profile.fy) <= 0:
        raise ValueError(f"{profile.id}: size and focal lengths must be positive")
    return profile


def load_camera_profile(path: Path) -> CameraProfile:
    return parse_camera_profile(json.loads(Path(path).read_text(encoding="utf-8")))


def profile_sensor_yaml(profile: CameraProfile, channel: int) -> str:
    """RTAB-Map's EuRoC `sensor.yaml` for one eye of the profile."""
    pinhole = render_cam_sensor_yaml(profile.calibration_spec(), channel)
    if profile.model == "pinhole":
        return pinhole
    coefficients = ", ".join(repr(c) for c in profile.distortion)
    return pinhole.replace(
        "distortion_model: radial-tangential\n", "distortion_model: equidistant\n"
    ).replace(
        "distortion_coefficients: [0.0, 0.0, 0.0, 0.0]\n",
        f"distortion_coefficients: [{coefficients}]\n",
    )
