"""Station surfaces: every dense region point assigned to one object surface.

A region (`surmap.slam.regions`) is one SAM mask's dense map-frame points
from one frame; by contract nothing accumulates there. The station gives
an object its shape by assigning each region's points to a *surface* that
lives for the whole run.

Identity is continuation, not SAM's track id (SAM 3.1 ids restart every
propagation window): a region whose points land where an earlier frame's
points were already assigned is that surface seen again. Concretely, on a
coarse match grid (default 10 cm, tolerant of stereo noise and viewpoint
change) the region's voxels already owned by a surface vote for it; the
most-voted surface continues when its votes reach `min_overlap` of the
region's match voxels, otherwise a new surface starts. A match voxel has
one owner: points falling on another surface's voxels stay that
surface's, and unowned voxels become the chosen surface's. Within a
surface, points are deduplicated on a fine grid (default 2 cm) so a
surface grows more complete, not unboundedly.

Motion: points are already map-frame (ego-motion compensated by the
RTAB-Map pose), so a static object's observations stay put. A surface
whose region centroid has drifted at least `moving_displacement_m`
(default 40 cm) from where it was first seen is *moving* — from then on,
for good: its accumulated points are the smear the object left, kept as
such and drawn as such, never mistaken for a static shape. Partial views
shift a centroid too; a large static object seen from very different
sides can be misclassified (architecture section 12 keeps the threshold
an open decision).

Surfaces are a separate layer on RTAB-Map's output, never written back
into its map (docs/architecture.md section 1).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

DEFAULT_VOXEL_M = 0.02
DEFAULT_MATCH_VOXEL_M = 0.10
DEFAULT_MIN_OVERLAP = 0.2
DEFAULT_MOVING_DISPLACEMENT_M = 0.4

# Voxel indices are packed into one int64: 21 bits per axis, offset to be
# non-negative — about +-21 km at 2 cm, far beyond any survey's map.
_AXIS_BITS = 21
_AXIS_OFFSET = 1 << (_AXIS_BITS - 1)


def _voxel_keys(points: NDArray[np.float32], size_m: float) -> NDArray[np.int64]:
    cells = np.floor(points.astype(np.float64) / size_m).astype(np.int64) + _AXIS_OFFSET
    return (cells[:, 0] << (2 * _AXIS_BITS)) | (cells[:, 1] << _AXIS_BITS) | cells[:, 2]


@dataclass(frozen=True)
class Surface:
    """One object's accumulated shape: one map-frame point per fine voxel."""

    surface_id: int
    label: str
    points: NDArray[np.float32]
    moving: bool = False


@dataclass(frozen=True)
class SurfaceAssignment:
    """Where one region's points went: the surface and the points newly added to it."""

    surface_id: int
    label: str
    track_id: int
    frame_id: int
    continued: bool
    points: NDArray[np.float32]
    total_points: int
    moving: bool = False


@dataclass
class _Shape:
    label: str
    first_centroid: NDArray[np.float64]
    moving: bool = False
    voxels: set[int] = field(default_factory=set)
    chunks: list[NDArray[np.float32]] = field(default_factory=list)
    count: int = 0


class SurfaceMap:
    """Assigns regions' points to surfaces (see module docs); ids start at 1."""

    def __init__(
        self,
        *,
        voxel_m: float = DEFAULT_VOXEL_M,
        match_voxel_m: float = DEFAULT_MATCH_VOXEL_M,
        min_overlap: float = DEFAULT_MIN_OVERLAP,
        moving_displacement_m: float = DEFAULT_MOVING_DISPLACEMENT_M,
    ) -> None:
        if voxel_m <= 0 or match_voxel_m <= 0:
            raise ValueError("voxel sizes must be positive")
        if not 0.0 < min_overlap <= 1.0:
            raise ValueError("min_overlap must be in (0, 1]")
        self._voxel_m = voxel_m
        self._match_voxel_m = match_voxel_m
        self._min_overlap = min_overlap
        self._moving_displacement_m = moving_displacement_m
        self._owners: dict[int, int] = {}  # match voxel -> surface id
        self._shapes: dict[int, _Shape] = {}
        self._version = 0

    @property
    def version(self) -> int:
        """Bumps on every assignment, so a renderer knows the layer changed."""
        return self._version

    def assign(
        self, frame_id: int, track_id: int, label: str, points: NDArray[np.float32]
    ) -> SurfaceAssignment | None:
        """Assign one region's points; None when the region has no points."""
        points = np.asarray(points, dtype=np.float32).reshape(-1, 3)
        if not len(points):
            return None
        match_keys = _voxel_keys(points, self._match_voxel_m)
        region_voxels = np.unique(match_keys)
        votes = Counter(
            owner for key in region_voxels.tolist() if (owner := self._owners.get(key)) is not None
        )
        surface_id, continued = self._choose(votes, len(region_voxels))
        centroid = points.astype(np.float64).mean(axis=0)
        if not continued:
            self._shapes[surface_id] = _Shape(label, centroid)
        shape = self._shapes[surface_id]
        drift = float(np.linalg.norm(centroid - shape.first_centroid))
        shape.moving = shape.moving or drift >= self._moving_displacement_m

        # Points on another surface's match voxels stay that surface's.
        mine = np.fromiter(
            (self._owners.get(key, surface_id) == surface_id for key in match_keys.tolist()),
            dtype=bool,
            count=len(match_keys),
        )
        candidates = points[mine]
        fine_keys = _voxel_keys(candidates, self._voxel_m)
        _, first = np.unique(fine_keys, return_index=True)
        fresh = [int(i) for i in np.sort(first) if int(fine_keys[i]) not in shape.voxels]
        added = candidates[fresh]
        shape.voxels.update(int(key) for key in fine_keys[fresh].tolist())
        for key in np.unique(match_keys[mine]).tolist():
            self._owners.setdefault(int(key), surface_id)
        if len(added):
            shape.chunks.append(added)
            shape.count += len(added)
        self._version += 1
        return SurfaceAssignment(
            surface_id=surface_id,
            label=shape.label,
            track_id=track_id,
            frame_id=frame_id,
            continued=continued,
            points=added,
            total_points=shape.count,
            moving=shape.moving,
        )

    def _choose(self, votes: Counter[int], region_voxels: int) -> tuple[int, bool]:
        if votes:
            # Most votes wins; ties go to the older surface.
            best, count = min(votes.items(), key=lambda item: (-item[1], item[0]))
            if count >= self._min_overlap * region_voxels:
                return best, True
        return len(self._shapes) + 1, False

    def surfaces(self) -> tuple[Surface, ...]:
        """Every surface so far, by id."""
        return tuple(
            Surface(
                surface_id,
                shape.label,
                np.concatenate(shape.chunks) if shape.chunks else np.zeros((0, 3), np.float32),
                shape.moving,
            )
            for surface_id, shape in sorted(self._shapes.items())
        )
