"""Stage 4 keypoints: FPS seeding, LK identity, one filter (design step 4).

TODO(n4): implemented by pr-4-moving-classification's Green row.
"""

from __future__ import annotations

from surmap.moving.config import MovingConfig
from surmap.types import Vec3


def select_keypoints(points: tuple[Vec3, ...], config: MovingConfig) -> tuple[Vec3, ...]:
    """Farthest-point sampling to at most config.max_keypoints seeds."""
    raise NotImplementedError("TODO(n4): select_keypoints")


class ConstantVelocityFilter:
    """One ego-motion-compensated constant-velocity Kalman filter."""

    def __init__(self) -> None:
        pass

    def update(self, t_ns: int, point: Vec3) -> Vec3:
        """Filter one camera-frame measurement."""
        raise NotImplementedError("TODO(n4): ConstantVelocityFilter.update")

    def predict(self, t_ns: int) -> Vec3:
        """Predict the point at `t_ns` (for <=3-frame holds)."""
        raise NotImplementedError("TODO(n4): ConstantVelocityFilter.predict")
