"""Rescaling a solved stereo estimate to a known baseline (RTAB-Map's option)."""

import pytest

from surmap.calibration.baseline import rescale_baseline
from surmap.calibration.port import LensModel, StereoEstimate


def an_estimate(translation_m: tuple[float, float, float]) -> StereoEstimate:
    return StereoEstimate(
        left_fx=381.0,
        left_fy=381.0,
        left_cx=320.0,
        left_cy=240.0,
        right_fx=381.0,
        right_fy=381.0,
        right_cx=320.0,
        right_cy=240.0,
        distortion_left=(0.0,) * 4,
        distortion_right=(0.0,) * 4,
        rotation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        translation_m=translation_m,
        baseline_m=sum(t * t for t in translation_m) ** 0.5,
        rms_left=0.1,
        rms_right=0.1,
        rms_stereo=0.1,
        views_used=20,
        lens=LensModel.PINHOLE_RADTAN,
    )


def test_the_translation_is_scaled_to_the_expected_baseline() -> None:
    # Given a solve that came back 2% long (a mis-measured square)
    solved = an_estimate((-0.0714, 0.0, 0.0))

    # When it is rescaled to the rig's known 7 cm
    rescaled = rescale_baseline(solved, expected_baseline_m=0.07)

    # Then the extrinsic is 7 cm and the scale says by how much it moved
    assert rescaled.baseline_m == pytest.approx(0.07)
    assert rescaled.translation_m[0] == pytest.approx(-0.07)
    assert rescaled.baseline_scale == pytest.approx(0.07 / 0.0714)
    assert rescaled.solved_baseline_m == pytest.approx(0.0714)
    assert rescaled.left_fx == solved.left_fx


def test_an_unscaled_estimate_reports_scale_one() -> None:
    # Given a solve with no rescale
    solved = an_estimate((-0.07, 0.0, 0.0))

    # Then its scale is one and its solved baseline is its baseline
    assert solved.baseline_scale == 1.0
    assert solved.solved_baseline_m == pytest.approx(0.07)


def test_a_non_positive_expected_baseline_is_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        rescale_baseline(an_estimate((-0.07, 0.0, 0.0)), expected_baseline_m=0.0)
