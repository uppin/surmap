"""The always-present, geometry-free summary of one reconstructed 3D object.

Field names follow `surmap.agent.v1.ObjectSummary` (proto/surmap/agent/v1/survey_tools.proto)
so the agent tools convert one into the other field by field.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np
from numpy.typing import NDArray

UpAxis = Literal["+y", "-y", "+z"]
"""The frame's up axis: `-y` for the demo's RTAB-Map map, `+z` for ENU snapshots."""

Vec3Tuple = tuple[float, float, float]
Matrix3 = tuple[Vec3Tuple, Vec3Tuple, Vec3Tuple]


class ShapeClass(Enum):
    """What an object's extent looks like, from its PCA eigenvalue ratios."""

    LINEAR = "linear"
    PLANAR = "planar"
    VOLUMETRIC = "volumetric"


class Relation(Enum):
    """How a neighbour sits relative to the object whose summary lists it."""

    ABOVE = "above"
    BELOW = "below"
    NEXT_TO = "next_to"
    OVERLAPS = "overlaps"


@dataclass(frozen=True)
class Obb:
    """An oriented bounding box from the PCA axes of the object's points.

    `extents` are half-lengths along the box's own axes, largest first. `rotation` is the
    row-major 3x3 matrix from box axes to the object frame: column `i` is box axis `i`.
    """

    centre: Vec3Tuple
    extents: Vec3Tuple
    rotation: Matrix3


@dataclass(frozen=True)
class Neighbour:
    """Another object close to this one."""

    id: str
    distance_m: float
    relation: Relation


@dataclass(frozen=True)
class ObjectSummary:
    """A compact description of one object, every coordinate in `frame`, metres."""

    id: str
    label: str
    confidence: float | None
    frame: str
    up_axis: UpAxis
    units: Literal["m"]
    n_points: int
    n_faces: int
    centroid: Vec3Tuple
    aabb_min: Vec3Tuple
    aabb_max: Vec3Tuple
    obb: Obb
    height_m: float
    footprint_m2: float
    shape: ShapeClass
    observed_frames: int
    t_first_ns: int | None
    t_last_ns: int | None
    neighbours: tuple[Neighbour, ...]
    geometry_uri: str | None


_UP_INDEX: dict[UpAxis, int] = {"+y": 1, "-y": 1, "+z": 2}
_UP_SIGN: dict[UpAxis, float] = {"+y": 1.0, "-y": -1.0, "+z": 1.0}

# A principal variance below this fraction of the next larger one collapses that dimension.
_COLLAPSED_RATIO = 0.1

Point2 = tuple[float, float]


def _checked_points(points: NDArray[np.float32]) -> NDArray[np.float32]:
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(f"points must be Nx3, got shape {points.shape}")
    if points.shape[0] == 0:
        raise ValueError("cannot summarise an empty point set")
    return points


def _vec3(values: NDArray[np.float64]) -> Vec3Tuple:
    x, y, z = (float(v) for v in values)
    return (x, y, z)


def _matrix3(m: NDArray[np.float64]) -> Matrix3:
    rows = [_vec3(row) for row in m]
    return (rows[0], rows[1], rows[2])


def _principal_axes(
    centred: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Right-handed principal axes (columns, largest variance first) and their variances."""
    covariance = centred.T @ centred / len(centred)
    variances, vectors = np.linalg.eigh(covariance)
    order = np.argsort(variances)[::-1]
    axes = vectors[:, order]
    if np.linalg.det(axes) < 0.0:
        axes[:, 2] = -axes[:, 2]
    return axes, np.clip(variances[order], 0.0, None)


def _shape_of(variances: NDArray[np.float64]) -> ShapeClass:
    largest, middle, smallest = (float(v) for v in variances)
    if middle <= _COLLAPSED_RATIO * largest:
        return ShapeClass.LINEAR
    if smallest <= _COLLAPSED_RATIO * middle:
        return ShapeClass.PLANAR
    return ShapeClass.VOLUMETRIC


def _cross(o: Point2, a: Point2, b: Point2) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _convex_hull_area(xy: NDArray[np.float64]) -> float:
    """Area of the convex hull of 2D points (monotone chain); 0 when they are collinear."""
    pts = sorted({(float(x), float(y)) for x, y in xy})
    if len(pts) < 3:
        return 0.0
    lower: list[Point2] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0.0:
            lower.pop()
        lower.append(p)
    upper: list[Point2] = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0.0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    x = np.array([p[0] for p in hull])
    y = np.array([p[1] for p in hull])
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def summarize(
    id: str,
    label: str,
    points: NDArray[np.float32],
    *,
    frame: str,
    up_axis: UpAxis,
    faces: NDArray[np.int32] | None = None,
    confidence: float | None = None,
    observed_frames: int = 0,
    t_first_ns: int | None = None,
    t_last_ns: int | None = None,
    geometry_uri: str | None = None,
) -> ObjectSummary:
    """Summarise an Nx3 point set (and its Mx3 faces, when present).

    `height_m` is the extent along `up_axis`; `footprint_m2` is the area of the points'
    footprint on the plane perpendicular to it. `neighbours` is empty — see `neighbours`.
    Raises `ValueError` for an empty or non-Nx3 point set.
    """
    cloud = _checked_points(points)
    xyz = cloud.astype(np.float64)
    centroid = xyz.mean(axis=0)
    axes, variances = _principal_axes(xyz - centroid)

    projected = (xyz - centroid) @ axes
    low, high = projected.min(axis=0), projected.max(axis=0)
    extents = (high - low) / 2.0
    local_centre = (high + low) / 2.0

    # Largest box axis first, so `extents[0]` is the box's length.
    order = np.argsort(-extents, kind="stable")
    axes, extents, local_centre = axes[:, order], extents[order], local_centre[order]

    up = _UP_INDEX[up_axis]
    lo, hi = xyz.min(axis=0), xyz.max(axis=0)
    return ObjectSummary(
        id=id,
        label=label,
        confidence=confidence,
        frame=frame,
        up_axis=up_axis,
        units="m",
        n_points=len(cloud),
        n_faces=0 if faces is None else len(faces),
        centroid=_vec3(centroid),
        aabb_min=_vec3(lo),
        aabb_max=_vec3(hi),
        obb=Obb(
            centre=_vec3(centroid + axes @ local_centre),
            extents=_vec3(extents),
            rotation=_matrix3(axes),
        ),
        height_m=float(hi[up] - lo[up]),
        footprint_m2=_convex_hull_area(xyz[:, [i for i in range(3) if i != up]]),
        shape=_shape_of(variances),
        observed_frames=observed_frames,
        t_first_ns=t_first_ns,
        t_last_ns=t_last_ns,
        neighbours=(),
        geometry_uri=geometry_uri,
    )


def neighbours(
    summary: ObjectSummary,
    others: Sequence[ObjectSummary],
    *,
    max_distance_m: float = 5.0,
    limit: int = 5,
) -> tuple[Neighbour, ...]:
    """The objects in `others` within `max_distance_m` of `summary`, nearest first.

    Distance is between the two axis-aligned boxes (0 when they touch or overlap); the
    relation says where the neighbour sits relative to `summary` along `summary.up_axis`.
    `summary` itself (same id) is never its own neighbour.
    """
    found: list[Neighbour] = []
    for other in others:
        if other.id == summary.id:
            continue
        gaps = _box_gaps(summary, other)
        distance = float(np.sqrt(np.sum(gaps * gaps)))
        if distance > max_distance_m:
            continue
        found.append(Neighbour(other.id, distance, _relation(summary, other, gaps)))
    return tuple(sorted(found, key=lambda n: n.distance_m)[:limit])


def _box_gaps(a: ObjectSummary, b: ObjectSummary) -> NDArray[np.float64]:
    """Per-axis gap between two AABBs; all zero when they touch or overlap."""
    a_lo, a_hi = np.asarray(a.aabb_min, dtype=np.float64), np.asarray(a.aabb_max, dtype=np.float64)
    b_lo, b_hi = np.asarray(b.aabb_min, dtype=np.float64), np.asarray(b.aabb_max, dtype=np.float64)
    gaps: NDArray[np.float64] = np.maximum(np.maximum(b_lo - a_hi, a_lo - b_hi), 0.0)
    return gaps


def _relation(summary: ObjectSummary, other: ObjectSummary, gaps: NDArray[np.float64]) -> Relation:
    if not gaps.any():
        return Relation.OVERLAPS
    up = _UP_INDEX[summary.up_axis]
    horizontal_clear = np.delete(gaps, up).any()
    if gaps[up] > 0.0 and not horizontal_clear:
        centre_offset = np.asarray(other.centroid, dtype=np.float64) - np.asarray(
            summary.centroid, dtype=np.float64
        )
        rises = _UP_SIGN[summary.up_axis] * float(centre_offset[up]) > 0.0
        return Relation.ABOVE if rises else Relation.BELOW
    return Relation.NEXT_TO
