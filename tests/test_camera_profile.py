"""The Bevy rig's camera profile: one file for the renderer and for RTAB-Map."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from surmap.simulation.calibration import render_cam_sensor_yaml
from surmap.simulation.camera_profile import (
    CameraProfile,
    Mount,
    load_camera_profile,
    parse_camera_profile,
    profile_sensor_yaml,
)

SHIPPED = (
    Path(__file__).parents[1]
    / "examples"
    / "bevy-sitl-poc"
    / "assets"
    / "cameras"
    / "elp-stereo-pinhole.camera.json"
)


def the_shipped_profile() -> CameraProfile:
    return load_camera_profile(SHIPPED)


def a_fisheye() -> CameraProfile:
    return replace(
        the_shipped_profile(),
        id="fisheye-test",
        model="fisheye_equidistant",
        distortion=(-0.013, 0.021, -0.012, 0.002),
    )


def test_the_shipped_profile_is_the_surmap_stereo_rig() -> None:
    # Given the profile the simulation renders with
    profile = the_shipped_profile()

    # Then it is the 640x480, 7 cm, 35-degree-down ELP rig
    assert (profile.model, profile.width, profile.height) == ("pinhole", 640, 480)
    assert (profile.fx, profile.cx, profile.cy, profile.baseline_m) == (381.36, 320.0, 240.0, 0.07)
    assert profile.mount == Mount(forward_m=0.30, up_m=0.10, pitch_deg=35.0)


def test_a_pinhole_profile_gives_rtabmap_the_rendered_calibration() -> None:
    # Given the shipped pinhole profile
    profile = the_shipped_profile()

    # When RTAB-Map's EuRoC sensor files are derived from it
    cam0, cam1 = profile_sensor_yaml(profile, 0), profile_sensor_yaml(profile, 1)

    # Then they are exactly the calibration the renderer's numbers make
    spec = profile.calibration_spec()
    assert (cam0, cam1) == (render_cam_sensor_yaml(spec, 0), render_cam_sensor_yaml(spec, 1))


def test_a_fisheye_profile_tells_rtabmap_its_equidistant_coefficients() -> None:
    # Given a fisheye profile
    profile = a_fisheye()

    # When its left sensor file is derived
    cam0 = profile_sensor_yaml(profile, 0)

    # Then RTAB-Map reads the equidistant model with k1..k4
    assert "distortion_model: equidistant\n" in cam0
    assert "distortion_coefficients: [-0.013, 0.021, -0.012, 0.002]\n" in cam0


def test_the_calibration_spec_carries_the_profile_identity_and_rate() -> None:
    # Given the shipped profile
    profile = the_shipped_profile()

    # When it is turned into the capture calibration
    spec = profile.calibration_spec()

    # Then the capture names the profile and its frame rate
    assert (spec.calibration_id, spec.rate_hz) == ("elp-stereo-pinhole-v1", 10.0)


def test_a_pinhole_with_distortion_is_refused() -> None:
    # Given the shipped profile's JSON with a radial term on a pinhole
    raw = json.loads(SHIPPED.read_text(encoding="utf-8"))
    raw["distortion"] = [0.1, 0.0, 0.0, 0.0]

    # Then it is refused, as the renderer refuses it
    with pytest.raises(ValueError, match="pinhole"):
        parse_camera_profile(raw)


def test_an_unknown_lens_model_is_refused() -> None:
    # Given a profile naming a model neither side implements
    raw = json.loads(SHIPPED.read_text(encoding="utf-8"))
    raw["model"] = "omnidirectional"

    # Then it is refused
    with pytest.raises(ValueError, match="model"):
        parse_camera_profile(raw)
