"""Stage 1: static-layer differencing (design section 4 step 1).

TODO(n3): implemented by pr-3-moving-differencing's Green row.
"""

from __future__ import annotations

from collections.abc import Iterable

from surmap.moving.candidates import CandidateCluster
from surmap.moving.config import MovingConfig
from surmap.types import Vec3


def tau(depth_m: float, theta_hat_rad: float, config: MovingConfig) -> float:
    """Noise-scaled differencing threshold tau(Z, theta_hat), in metres."""
    raise NotImplementedError("TODO(n3): tau(Z, theta_hat)")


class StaticLayer:
    """Voxel-hash static reference with log-odds occupancy and decay."""

    def __init__(self, config: MovingConfig) -> None:
        self._config = config

    @property
    def voxel_count(self) -> int:
        """Live voxels, counted against the config cap."""
        raise NotImplementedError("TODO(n3): voxel_count")

    def seed(self, points: Iterable[Vec3]) -> None:
        """Seed/refresh the layer from an RTAB-Map exported cloud."""
        raise NotImplementedError("TODO(n3): seed")

    def is_occupied(self, point: Vec3) -> bool:
        """Whether `point`'s voxel is static-occupied."""
        raise NotImplementedError("TODO(n3): is_occupied")

    def difference(
        self, frame_id: int, t_ns: int, points: Iterable[Vec3]
    ) -> tuple[CandidateCluster, ...]:
        """Dynamic candidate clusters in `points`, cluster-persistent only."""
        raise NotImplementedError("TODO(n3): difference")
