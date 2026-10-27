"""Stage 1: static-layer differencing (design section 4 step 1)."""

from __future__ import annotations

import math
from collections.abc import Iterable

from surmap.moving.candidates import CandidateCluster
from surmap.moving.config import MovingConfig
from surmap.types import Vec3

_STATIC_LOG_ODDS = 3.0
_CANDIDATE_LOG_ODDS = -1.0


def tau(depth_m: float, theta_hat_rad: float, config: MovingConfig) -> float:
    """Noise-scaled differencing threshold tau(Z, theta_hat), in metres.

    Stereo depth error grows with Z^2/(f*B); a held-pose rotation
    error theta maps to lateral world error theta*Z.
    """
    depth_term = config.tau_depth_k * depth_m * depth_m / (config.focal_px * config.baseline_m)
    rotation_term = config.tau_rotation_k * abs(theta_hat_rad) * depth_m
    return config.tau0_m + depth_term + rotation_term


class StaticLayer:
    """Voxel-hash static reference with log-odds occupancy and decay."""

    def __init__(self, config: MovingConfig) -> None:
        self._config = config
        self._log_odds: dict[tuple[int, int, int], float] = {}

    def _key(self, point: Vec3) -> tuple[int, int, int]:
        size = self._config.voxel_size_m
        return (
            math.floor(point.x / size),
            math.floor(point.y / size),
            math.floor(point.z / size),
        )

    @property
    def voxel_count(self) -> int:
        """Live voxels, counted against the config cap."""
        return len(self._log_odds)

    def seed(self, points: Iterable[Vec3]) -> None:
        """Seed/refresh the layer from an RTAB-Map exported cloud."""
        for point in points:
            self._log_odds[self._key(point)] = _STATIC_LOG_ODDS
        self._enforce_cap()

    def refresh(self, points: Iterable[Vec3]) -> None:
        """Re-seed at flush (n5 wiring); alias of `seed`."""
        self.seed(points)

    def _enforce_cap(self) -> None:
        cap = self._config.max_voxels
        if len(self._log_odds) <= cap:
            return
        size = self._config.voxel_size_m
        by_distance = sorted(
            self._log_odds,
            key=lambda key: (key[0] * size) ** 2 + (key[1] * size) ** 2 + (key[2] * size) ** 2,
            reverse=True,
        )
        for key in by_distance[: len(self._log_odds) - cap]:
            del self._log_odds[key]

    def is_occupied(self, point: Vec3) -> bool:
        """Whether `point`'s voxel is static-occupied."""
        return self._log_odds.get(self._key(point), _CANDIDATE_LOG_ODDS) > 0.0

    def _is_static(self, point: Vec3, theta_hat_rad: float) -> bool:
        if self.is_occupied(point):
            return True
        depth = math.sqrt(point.x**2 + point.y**2 + point.z**2)
        radius = math.ceil(tau(depth, theta_hat_rad, self._config) / self._config.voxel_size_m)
        if radius > 24:  # bound the neighbourhood search; own-voxel check already ran
            radius = 24
        key = self._key(point)
        size = self._config.voxel_size_m
        threshold = tau(depth, theta_hat_rad, self._config)
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    if self._log_odds.get((key[0] + dx, key[1] + dy, key[2] + dz), -1.0) <= 0:
                        continue
                    center = Vec3(
                        (key[0] + dx + 0.5) * size,
                        (key[1] + dy + 0.5) * size,
                        (key[2] + dz + 0.5) * size,
                    )
                    if (center - point).norm() <= threshold:
                        return True
        return False

    def difference(
        self,
        frame_id: int,
        t_ns: int,
        points: Iterable[Vec3],
        theta_hat_rad: float = 0.0,
    ) -> tuple[CandidateCluster, ...]:
        """Dynamic candidate clusters in `points`, cluster-persistent only.

        Persistence is per connected cluster (never per voxel), so a
        fast mover that never revisits a voxel still forms a cluster
        every frame. Differenced points are never absorbed into the
        layer (the dwell test is `seed`/`refresh` only).
        """
        candidates = [point for point in points if not self._is_static(point, theta_hat_rad)]
        clusters: list[list[Vec3]] = []
        remaining = list(candidates)
        while remaining:
            seed_point = remaining.pop()
            cluster = [seed_point]
            queue = [seed_point]
            while queue:
                current = queue.pop()
                neighbours = [
                    point
                    for point in remaining
                    if max(
                        abs(point.x - current.x),
                        abs(point.y - current.y),
                        abs(point.z - current.z),
                    )
                    <= self._config.voxel_size_m * 2.5
                ]
                for neighbour in neighbours:
                    remaining.remove(neighbour)
                    cluster.append(neighbour)
                    queue.append(neighbour)
            clusters.append(cluster)
        result: list[CandidateCluster] = []
        for cluster in clusters:
            if len(cluster) < self._config.min_cluster_points:
                continue
            depths = [math.sqrt(p.x**2 + p.y**2 + p.z**2) for p in cluster]
            result.append(
                CandidateCluster(
                    frame_id=frame_id,
                    t_ns=t_ns,
                    points=tuple(cluster),
                    depth_min_m=min(depths),
                    depth_max_m=max(depths),
                )
            )
        return tuple(result)
