"""A solved stereo estimate exported as the EuRoC cam0/cam1 `sensor.yaml` pair."""

import dataclasses
import math
import re

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.calibration.export import estimated_sensor_yamls
from surmap.calibration.port import LensModel, StereoEstimate

YAW = math.radians(1.0)


def an_estimate() -> StereoEstimate:
    """A slightly toed-in rig: right eye yawed 1°, 7 cm to the side."""
    return StereoEstimate(
        left_fx=381.0,
        left_fy=382.0,
        left_cx=321.0,
        left_cy=239.0,
        right_fx=379.0,
        right_fy=380.0,
        right_cx=318.0,
        right_cy=242.0,
        distortion_left=(-0.28, 0.07, 0.001, -0.002),
        distortion_right=(-0.27, 0.06, -0.001, 0.002),
        rotation=(
            math.cos(YAW),
            0.0,
            math.sin(YAW),
            0.0,
            1.0,
            0.0,
            -math.sin(YAW),
            0.0,
            math.cos(YAW),
        ),
        translation_m=(-0.07, 0.001, 0.0),
        baseline_m=math.hypot(0.07, 0.001),
        rms_left=0.2,
        rms_right=0.2,
        rms_stereo=0.3,
        views_used=20,
        lens=LensModel.PINHOLE_RADTAN,
    )


def numbers_after(text: str, key: str) -> list[float]:
    """The bracketed list after `key:`, read the way the sidecar reads it."""
    match = re.search(rf"{key}:\s*\[([^\]]*)\]", text)
    assert match is not None, f"{key} missing"
    return [float(v) for v in match.group(1).split(",")]


def t_bs(text: str) -> NDArray[np.float64]:
    return np.array(numbers_after(text, "data"), dtype=np.float64).reshape(4, 4)


def test_each_eye_keeps_its_own_intrinsics_and_distortion() -> None:
    # When the estimate is exported
    cam0, cam1 = estimated_sensor_yamls(an_estimate(), width=640, height=480)

    # Then cam0 is the left eye and cam1 the right, distortion included
    assert numbers_after(cam0, "intrinsics") == [381.0, 382.0, 321.0, 239.0]
    assert numbers_after(cam1, "intrinsics") == [379.0, 380.0, 318.0, 242.0]
    assert numbers_after(cam0, "distortion_coefficients") == [-0.28, 0.07, 0.001, -0.002]
    assert numbers_after(cam1, "distortion_coefficients") == [-0.27, 0.06, -0.001, 0.002]
    assert numbers_after(cam0, "resolution") == [640, 480]


def test_the_two_body_poses_reproduce_the_solved_extrinsic() -> None:
    # When the estimate is exported
    estimate = an_estimate()
    cam0, cam1 = estimated_sensor_yamls(estimate, width=640, height=480)

    # Then left-in-right, as the streaming sidecar derives it, is the solved [R|T]
    left_in_right = np.linalg.inv(t_bs(cam1)) @ t_bs(cam0)
    expected = np.eye(4)
    expected[:3, :3] = np.array(estimate.rotation).reshape(3, 3)
    expected[:3, 3] = estimate.translation_m
    assert left_in_right == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("lens", [LensModel.PINHOLE_RATIONAL, LensModel.FISHEYE])
def test_a_lens_the_streaming_sidecar_cannot_rectify_is_not_exported(lens: LensModel) -> None:
    # Given an estimate solved with a rational or fisheye lens model
    estimate = dataclasses.replace(an_estimate(), lens=lens)

    # Then export refuses it rather than write yamls read as radial-tangential
    with pytest.raises(ValueError, match="radial-tangential"):
        estimated_sensor_yamls(estimate, width=640, height=480)
