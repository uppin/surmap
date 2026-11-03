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
    raise NotImplementedError  # TODO(pr-3): implement


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
    raise NotImplementedError  # TODO(pr-3): implement
