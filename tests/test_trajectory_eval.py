"""Rigid (no-scale) trajectory alignment and ATE against ground truth."""

import numpy as np
import pytest
from surmap.simulation.trajectory_eval import align_rigid, ate_rmse

SOURCE = np.array(
    [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 1.0, 1.0],
        [2.0, 0.5, 0.25],
    ]
)
ROTATION_Z_90 = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
TRANSLATION = np.array([1.0, 2.0, 3.0])


def test_alignment_recovers_a_known_rotation_and_translation() -> None:
    # Given ground truth moved by a quarter turn about up and (1, 2, 3)
    target = SOURCE @ ROTATION_Z_90.T + TRANSLATION

    # When the estimate is rigidly aligned onto the ground truth
    alignment = align_rigid(SOURCE, target)

    # Then the known motion is recovered and the aligned ATE vanishes
    np.testing.assert_allclose(alignment.rotation, ROTATION_Z_90, atol=1e-9)
    np.testing.assert_allclose(alignment.translation, TRANSLATION, atol=1e-9)
    np.testing.assert_allclose(alignment.apply(SOURCE), target, atol=1e-9)
    assert ate_rmse(alignment.apply(SOURCE), target) == pytest.approx(0.0, abs=1e-9)


def test_ate_of_a_noisy_copy_is_the_noise_scale() -> None:
    # Given a copy of the trajectory with fixed five-centimetre noise
    noisy = SOURCE + np.random.default_rng(42).normal(0.0, 0.05, SOURCE.shape)

    # When its ATE against the original is measured
    error = ate_rmse(noisy, SOURCE)

    # Then it lands at the noise scale, neither zero nor metres
    assert 0.02 < error < 0.10


def test_alignment_refuses_fewer_than_three_points() -> None:
    # Given only two corresponding points
    two_points = SOURCE[:2]

    # When they are aligned, Then a value error is raised
    with pytest.raises(ValueError):
        align_rigid(two_points, two_points)


def test_alignment_refuses_mismatched_shapes() -> None:
    # Given four estimates for six ground-truth points
    short = SOURCE[:4]

    # When they are aligned, Then a value error is raised
    with pytest.raises(ValueError):
        align_rigid(short, SOURCE)


def test_ate_refuses_mismatched_shapes() -> None:
    # Given four estimates for six ground-truth points
    short = SOURCE[:4]

    # When their ATE is measured, Then a value error is raised
    with pytest.raises(ValueError):
        ate_rmse(short, SOURCE)


def test_alignment_never_scales_a_doubled_trajectory_to_fit() -> None:
    # Given a ground truth twice the size of the estimate
    doubled = SOURCE * 2.0

    # When the estimate is rigidly aligned onto it
    aligned = align_rigid(SOURCE, doubled).apply(SOURCE)

    # Then a real error remains, because no scale was estimated
    assert ate_rmse(aligned, doubled) > 0.5
