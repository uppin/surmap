"""Rigid (no-scale) trajectory alignment and ATE."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Points = NDArray[np.float64]


def _checked(estimate: Points, truth: Points) -> tuple[Points, Points]:
    est = np.asarray(estimate, dtype=np.float64)
    ref = np.asarray(truth, dtype=np.float64)
    if est.shape != ref.shape:
        raise ValueError(f"shape mismatch: {est.shape} vs {ref.shape}")
    if est.ndim != 2 or est.shape[1] != 3:
        raise ValueError(f"trajectories must be Nx3, got {est.shape}")
    return est, ref


@dataclass(frozen=True)
class RigidAlignment:
    rotation: Points
    translation: Points

    def apply(self, points: Points) -> Points:
        pts = np.asarray(points, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != 3:
            raise ValueError(f"points must be Nx3, got {pts.shape}")
        result: Points = pts @ self.rotation.T + self.translation
        return result


def align_rigid(estimate: Points, truth: Points) -> RigidAlignment:
    est, ref = _checked(estimate, truth)
    if est.shape[0] < 3:
        raise ValueError("rigid alignment needs at least three points")
    est_centroid = est.mean(axis=0)
    ref_centroid = ref.mean(axis=0)
    est_centred = est - est_centroid
    ref_centred = ref - ref_centroid
    u, _, vt = np.linalg.svd(est_centred.T @ ref_centred)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt = vt.copy()
        vt[-1, :] *= -1.0
        rotation = vt.T @ u.T
    translation = ref_centroid - rotation @ est_centroid
    return RigidAlignment(
        rotation=np.asarray(rotation, dtype=np.float64),
        translation=np.asarray(translation, dtype=np.float64),
    )


def ate_rmse(estimate: Points, truth: Points) -> float:
    est, ref = _checked(estimate, truth)
    if est.shape[0] == 0:
        raise ValueError("ATE needs at least one point")
    return float(np.sqrt(np.mean(np.sum((est - ref) ** 2, axis=1))))


def similarity_scale(estimate: Points, truth: Points) -> float:
    """Umeyama's scale: how much the estimate must be stretched to fit the truth.

    1.0 is a metric estimate; a stereo rig with a mis-stated baseline or
    focal length shows up here as a steady ratio.
    """
    est, ref = _checked(estimate, truth)
    est_c = est - est.mean(axis=0)
    ref_c = ref - ref.mean(axis=0)
    covariance = ref_c.T @ est_c / len(est)
    u, singular, vt = np.linalg.svd(covariance)
    sign = np.ones(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        sign[2] = -1.0
    variance = float((est_c**2).sum() / len(est))
    return float((singular * sign).sum() / variance)
