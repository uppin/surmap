"""Stage 4 keypoints: FPS seeding, LK identity, one filter (design step 4)."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from surmap.moving.config import MovingConfig
from surmap.types import Vec3


def select_keypoints(points: tuple[Vec3, ...], config: MovingConfig) -> tuple[Vec3, ...]:
    """Farthest-point sampling to at most config.max_keypoints seeds."""
    if not points:
        return ()
    cap = min(config.max_keypoints, len(points))
    centroid = Vec3(
        sum(p.x for p in points) / len(points),
        sum(p.y for p in points) / len(points),
        sum(p.z for p in points) / len(points),
    )
    first = max(points, key=lambda p: (p - centroid).norm())
    chosen: list[Vec3] = [first]
    while len(chosen) < cap:
        nxt = max(points, key=lambda p: min((p - c).norm() for c in chosen))
        if nxt in chosen:
            break
        chosen.append(nxt)
    return tuple(chosen)


def lk_track(
    previous: NDArray[np.float32],
    current: NDArray[np.float32],
    points_xy: tuple[tuple[float, float], ...],
    window: int = 21,
    max_shift_px: float = 10.0,
) -> tuple[tuple[float, float] | None, ...]:
    """Bounded Lucas-Kanade tracking of seed pixels between two frames.

    Returns the tracked (x, y) per seed, or None where the LK
    system is singular or the shift exceeds `max_shift_px` (the
    caller re-seeds those from current candidates).
    """
    if previous.shape != current.shape or previous.ndim != 2:
        raise ValueError("LK frames must be same-shape grayscale arrays")
    grad_x = np.gradient(current, axis=1)
    grad_y = np.gradient(current, axis=0)
    half = window // 2
    height, width = current.shape
    results: list[tuple[float, float] | None] = []
    for x, y in points_xy:
        cx, cy = int(round(x)), int(round(y))
        if cx - half < 0 or cy - half < 0 or cx + half >= width or cy + half >= height:
            results.append(None)
            continue
        patch_prev = previous[cy - half : cy + half + 1, cx - half : cx + half + 1]
        patch_cur = current[cy - half : cy + half + 1, cx - half : cx + half + 1]
        gx = grad_x[cy - half : cy + half + 1, cx - half : cx + half + 1]
        gy = grad_y[cy - half : cy + half + 1, cx - half : cx + half + 1]
        dt = (patch_cur - patch_prev).astype(np.float64)
        a = np.array(
            [
                [float((gx * gx).sum()), float((gx * gy).sum())],
                [float((gx * gy).sum()), float((gy * gy).sum())],
            ]
        )
        b = np.array([-float((gx * dt).sum()), -float((gy * dt).sum())])
        try:
            shift = np.linalg.solve(a, b)
        except np.linalg.LinAlgError:
            results.append(None)
            continue
        if float(np.hypot(shift[0], shift[1])) > max_shift_px:
            results.append(None)
            continue
        results.append((x + float(shift[0]), y + float(shift[1])))
    return tuple(results)


class ConstantVelocityFilter:
    """One ego-motion-compensated constant-velocity filter (camera frame).

    A single alpha-beta (constant-velocity Kalman) filter: the
    caller removes ego motion before `update`, so the filter sees
    object motion only. No second image-space filter is chained.
    """

    def __init__(self, alpha: float = 0.5, beta: float = 0.1) -> None:
        self._alpha = alpha
        self._beta = beta
        self._position: Vec3 | None = None
        self._velocity = Vec3(0.0, 0.0, 0.0)
        self._t_ns: int | None = None

    def _predict_at(self, t_ns: int) -> Vec3:
        assert self._position is not None and self._t_ns is not None
        dt = (t_ns - self._t_ns) / 1e9
        return Vec3(
            self._position.x + self._velocity.x * dt,
            self._position.y + self._velocity.y * dt,
            self._position.z + self._velocity.z * dt,
        )

    def update(self, t_ns: int, point: Vec3) -> Vec3:
        """Filter one camera-frame measurement."""
        if self._position is None or self._t_ns is None:
            self._position, self._t_ns = point, t_ns
            return point
        dt = max((t_ns - self._t_ns) / 1e9, 1e-6)
        predicted = self._predict_at(t_ns)
        residual = point - predicted
        position = Vec3(
            predicted.x + self._alpha * residual.x,
            predicted.y + self._alpha * residual.y,
            predicted.z + self._alpha * residual.z,
        )
        self._velocity = Vec3(
            self._velocity.x + (self._beta / dt) * residual.x * 0.1,
            self._velocity.y + (self._beta / dt) * residual.y * 0.1,
            self._velocity.z + (self._beta / dt) * residual.z * 0.1,
        )
        self._position, self._t_ns = position, t_ns
        return position

    def predict(self, t_ns: int) -> Vec3:
        """Predict the point at `t_ns` (for <=3-frame holds)."""
        if self._position is None:
            raise ValueError("filter has no measurement yet")
        return self._predict_at(t_ns)
