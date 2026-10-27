"""Stage 1: static-layer differencing (design section 4 step 1).

Hot path (design section 2: 5 Hz, <=4k points, 1 CM5 core): the
static test is an occupied-voxel set lookup plus a block-index
nearest-voxel search bounded by tau; clustering is voxel
adjacency over a dict. No per-point neighbourhood scans.

Occupancy is log-odds with lazy decay: each voxel stores
(value, frame); the effective value decays per analyzed frame
unless re-observed, so absorbed ghosts expire. A voxel becomes
static only by dwelling: `observe_frame` adds a small increment
per frame, and the occupied threshold needs several frames of
agreement (RTAB seeding sets it outright).
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np

from surmap.moving.candidates import CandidateCluster
from surmap.moving.config import MovingConfig
from surmap.types import Vec3

_SEED_LOG_ODDS = 3.0
_DWELL_INCREMENT = 0.6
_CANDIDATE_PENALTY = 0.5
_DECAY_PER_FRAME = 0.03
_OCCUPIED_THRESHOLD = 1.5


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
        self._voxels: dict[tuple[int, int, int], tuple[float, int]] = {}
        self._frame = 0
        self._occ_cache: tuple[set[tuple[int, int, int]], np.ndarray] | None = None

    def _key(self, point: Vec3) -> tuple[int, int, int]:
        size = self._config.voxel_size_m
        return (
            math.floor(point.x / size),
            math.floor(point.y / size),
            math.floor(point.z / size),
        )

    def _effective(self, key: tuple[int, int, int]) -> float:
        entry = self._voxels.get(key)
        if entry is None:
            return -1.0
        value, frame = entry
        return value - _DECAY_PER_FRAME * max(0, self._frame - frame)

    @property
    def voxel_count(self) -> int:
        """Occupied voxels, counted against the config cap."""
        return sum(1 for key in self._voxels if self._effective(key) >= _OCCUPIED_THRESHOLD)

    def seed(self, points: Iterable[Vec3]) -> None:
        """Seed/refresh the layer from an RTAB-Map exported cloud."""
        for point in points:
            self._voxels[self._key(point)] = (_SEED_LOG_ODDS, self._frame)
        self._enforce_cap()

    def refresh(self, points: Iterable[Vec3]) -> None:
        """Re-seed at flush (n5 wiring); alias of `seed`."""
        self.seed(points)

    def observe_frame(self, points: Iterable[Vec3]) -> None:
        """Dwell-gated extension: one small increment per voxel per frame.

        A voxel turns static only after several frames agree on
        it, so a slow mover passing through (a frame or two per
        voxel) is never absorbed.
        """
        self._frame += 1
        seen: set[tuple[int, int, int]] = set()
        for point in points:
            key = self._key(point)
            if key in seen:
                continue
            seen.add(key)
            current = self._effective(key) if key in self._voxels else 0.0
            self._voxels[key] = (current + _DWELL_INCREMENT, self._frame)
        self._enforce_cap()

    def _enforce_cap(self) -> None:
        cap = self._config.max_voxels
        if len(self._voxels) <= cap:
            return
        size = self._config.voxel_size_m
        by_distance = sorted(
            self._voxels,
            key=lambda key: (key[0] * size) ** 2 + (key[1] * size) ** 2 + (key[2] * size) ** 2,
            reverse=True,
        )
        for key in by_distance[: len(self._voxels) - cap]:
            del self._voxels[key]

    def is_occupied(self, point: Vec3) -> bool:
        """Whether `point`'s voxel is static-occupied."""
        return self._effective(self._key(point)) >= _OCCUPIED_THRESHOLD

    def _occupied_keys(self) -> set[tuple[int, int, int]]:
        return {key for key in self._voxels if self._effective(key) >= _OCCUPIED_THRESHOLD}

    def _near_occupied(self, point: Vec3, occupied: set[tuple[int, int, int]]) -> bool:
        """Own voxel or any of the 26 neighbours occupied (fast path)."""
        key = self._key(point)
        if key in occupied:
            return True
        return any(
            (key[0] + dx, key[1] + dy, key[2] + dz) in occupied
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for dz in (-1, 0, 1)
        )

    def _exact_static_mask(
        self,
        points: list[Vec3],
        occupied: set[tuple[int, int, int]],
        theta_hat_rad: float,
    ) -> list[bool]:
        """Exact nearest-occupied-voxel test for the fast-path misses.

        Chunked numpy distance computation against occupied voxel
        centres, box-filtered to the points' neighbourhood first.
        """
        if not points:
            return []
        if not occupied:
            return [False] * len(points)
        size = self._config.voxel_size_m
        if self._occ_cache is not None and self._occ_cache[0] == occupied:
            occ = self._occ_cache[1]
        else:
            occ = np.array(
                [[(k[0] + 0.5) * size, (k[1] + 0.5) * size, (k[2] + 0.5) * size] for k in occupied],
                dtype=np.float64,
            )
            self._occ_cache = (occupied, occ)
        pts = np.array([[p.x, p.y, p.z] for p in points], dtype=np.float64)
        depths = np.sqrt((pts * pts).sum(axis=1))
        cfg = self._config
        thresholds = (
            cfg.tau0_m
            + cfg.tau_depth_k * depths * depths / (cfg.focal_px * cfg.baseline_m)
            + cfg.tau_rotation_k * abs(theta_hat_rad) * depths
        )
        margin = float(thresholds.max()) if len(thresholds) else 0.0
        lo = pts.min(axis=0) - margin
        hi = pts.max(axis=0) + margin
        occ = occ[np.all((occ >= lo) & (occ <= hi), axis=1)]
        if len(occ) == 0:
            return [False] * len(points)
        # Coarse gate: points farther than threshold + cell half
        # diagonal from every 1 m coarse cell centre are candidates
        # without the fine distance computation.
        coarse = np.unique(np.floor(occ / 1.0), axis=0) + 0.5
        coarse_sq = (coarse * coarse).sum(axis=1)
        pts_sq_all = (pts * pts).sum(axis=1)
        coarse_nearest_sq = np.full(len(pts), np.inf)
        for start in range(0, len(coarse), 8192):
            chunk = coarse[start : start + 8192]
            dist_sq = pts_sq_all[:, None] + coarse_sq[None, :] - 2.0 * (pts @ chunk.T)
            coarse_nearest_sq = np.minimum(coarse_nearest_sq, dist_sq.min(axis=1))
        far = np.sqrt(np.maximum(coarse_nearest_sq, 0.0)) > thresholds + 0.87
        result = [False] * len(points)
        near_idx = [i for i in range(len(points)) if not far[i]]
        if not near_idx:
            return result
        pts = pts[near_idx]
        thresholds = thresholds[near_idx]
        # Squared distances via BLAS: |p-o|^2 = |p|^2 + |o|^2 - 2 p.o
        pts_sq = (pts * pts).sum(axis=1)
        nearest_sq = np.full(len(pts), np.inf)
        for start in range(0, len(occ), 8192):
            chunk = occ[start : start + 8192]
            dist_sq = pts_sq[:, None] + (chunk * chunk).sum(axis=1)[None, :] - 2.0 * (pts @ chunk.T)
            nearest_sq = np.minimum(nearest_sq, dist_sq.min(axis=1))
        for index, d2, t in zip(near_idx, nearest_sq, thresholds, strict=True):
            result[index] = bool(d2 <= t * t)
        return result

    def difference(
        self,
        frame_id: int,
        t_ns: int,
        points: Iterable[Vec3],
        theta_hat_rad: float = 0.0,
    ) -> tuple[CandidateCluster, ...]:
        """Dynamic candidate clusters in `points`, cluster-persistent only.

        Persistence is per connected cluster (never per voxel), so
        a fast mover that never revisits a voxel still forms a
        cluster every frame. Candidate voxels take a log-odds
        penalty (never a reward): differenced movers are not
        absorbed, and previously absorbed ghosts decay away.
        """
        self._frame += 1
        occupied = self._occupied_keys()
        point_list = list(points)
        misses = [p for p in point_list if not self._near_occupied(p, occupied)]
        exact = self._exact_static_mask(misses, occupied, theta_hat_rad)
        static_misses = {id(p) for p, is_static in zip(misses, exact, strict=True) if is_static}
        candidates = [p for p in misses if id(p) not in static_misses]
        penalized: set[tuple[int, int, int]] = set()
        for point in candidates:
            key = self._key(point)
            if key in penalized or key not in self._voxels:
                continue
            penalized.add(key)
            self._voxels[key] = (self._effective(key) - _CANDIDATE_PENALTY, self._frame)
        # Cluster candidates by grid hashing: points within one
        # cell (3 voxels) of each other are connected. Scattered
        # candidates stay isolated without a neighbourhood scan.
        cell = self._config.voxel_size_m * 3.0

        def cell_key(point: Vec3) -> tuple[int, int, int]:
            return (
                math.floor(point.x / cell),
                math.floor(point.y / cell),
                math.floor(point.z / cell),
            )

        grid: dict[tuple[int, int, int], list[Vec3]] = {}
        for point in candidates:
            grid.setdefault(cell_key(point), []).append(point)
        clusters: list[list[Vec3]] = []
        seen: set[int] = set()
        for point in candidates:
            if id(point) in seen:
                continue
            cluster = [point]
            seen.add(id(point))
            queue = [point]
            while queue:
                current = queue.pop()
                key = cell_key(current)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for dz in (-1, 0, 1):
                            for other in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                                if id(other) in seen:
                                    continue
                                delta = other - current
                                if delta.x**2 + delta.y**2 + delta.z**2 <= cell * cell:
                                    seen.add(id(other))
                                    cluster.append(other)
                                    queue.append(other)
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
