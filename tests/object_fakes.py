"""Builders and matchers for the object 3D contract tests."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

from surmap.objects3d import (
    Neighbour,
    Obb,
    ObjectSummary,
    Relation,
    ShapeClass,
    UpAxis,
    summarize,
)

Vec3Tuple = tuple[float, float, float]

# --- builders --------------------------------------------------------------------------------


def a_box(
    centre: Vec3Tuple = (0.0, 0.0, 0.0),
    half: Vec3Tuple = (2.0, 1.0, 0.5),
    yaw_deg: float = 0.0,
    spacing: float = 0.1,
) -> NDArray[np.float32]:
    """A solid lattice box, yawed about +z, so its extents and axes are exact."""
    axes = [np.linspace(-h, h, round(2 * h / spacing) + 1) for h in half]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    yaw = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    cloud: NDArray[np.float32] = (grid @ yaw.T + np.array(centre)).astype(np.float32)
    return cloud


def a_plane(seed: int = 3) -> NDArray[np.float32]:
    """A 3 m x 2 m patch in the x-y plane with 3 mm of noise across it."""
    rng = np.random.default_rng(seed)
    xy = rng.uniform((-1.5, -1.0), (1.5, 1.0), size=(5_000, 2))
    z = rng.normal(0.0, 0.003, size=(5_000, 1))
    return np.hstack([xy, z]).astype(np.float32)


def a_pole(seed: int = 3) -> NDArray[np.float32]:
    """A 4 m tall pole of 5 cm radius standing on z = 0."""
    rng = np.random.default_rng(seed)
    angle = rng.uniform(0.0, 2 * math.pi, size=5_000)
    radius = 0.05 * np.sqrt(rng.uniform(0.0, 1.0, size=5_000))
    z = rng.uniform(0.0, 4.0, size=5_000)
    return np.stack([radius * np.cos(angle), radius * np.sin(angle), z], axis=1).astype(np.float32)


def a_noisy_box(n: int = 14_000, seed: int = 3) -> NDArray[np.float32]:
    """A car-sized cloud far from the map origin, with 1 cm of sensor noise."""
    rng = np.random.default_rng(seed)
    inside = rng.uniform((-2.0, -0.75, -1.0), (2.0, 0.75, 1.0), size=(n, 3))
    noise = rng.normal(0.0, 0.01, size=(n, 3))
    cloud: NDArray[np.float32] = (inside + noise + np.array((412.35, -88.10, 2.04))).astype(
        np.float32
    )
    return cloud


def a_square() -> NDArray[np.float32]:
    """Four corners of a 1 m square in the x-z plane around (412.35, -88.10, 2.04)."""
    offsets = np.array([(-0.5, 0.0, -0.5), (0.5, 0.0, -0.5), (0.5, 0.0, 0.5), (-0.5, 0.0, 0.5)])
    cloud: NDArray[np.float32] = (offsets + np.array((412.35, -88.10, 2.04))).astype(np.float32)
    return cloud


def two_triangles() -> NDArray[np.int32]:
    """The square split along its diagonal, 0-based."""
    return np.array([(0, 1, 2), (0, 2, 3)], dtype=np.int32)


def the_square_colours() -> NDArray[np.uint8]:
    return np.array([(158, 156, 153), (200, 10, 10), (10, 200, 10), (10, 10, 200)], dtype=np.uint8)


def a_summary_of(
    points: NDArray[np.float32],
    id: str = "obj_17",
    label: str = "car",
    up_axis: UpAxis = "-y",
) -> ObjectSummary:
    """A hand-built summary around the points' box — independent of `summarize`."""
    lo = tuple(float(v) for v in points.min(axis=0))
    hi = tuple(float(v) for v in points.max(axis=0))
    centre = tuple((a + b) / 2 for a, b in zip(lo, hi, strict=True))
    extents = tuple((b - a) / 2 for a, b in zip(lo, hi, strict=True))
    return ObjectSummary(
        id=id,
        label=label,
        confidence=0.9,
        frame="map",
        up_axis=up_axis,
        units="m",
        n_points=len(points),
        n_faces=0,
        centroid=vec3(points.mean(axis=0)),
        aabb_min=vec3(lo),
        aabb_max=vec3(hi),
        obb=Obb(
            centre=vec3(centre),
            extents=vec3(extents),
            rotation=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        ),
        height_m=0.0,
        footprint_m2=0.0,
        shape=ShapeClass.VOLUMETRIC,
        observed_frames=1,
        t_first_ns=None,
        t_last_ns=None,
        neighbours=(),
        geometry_uri=None,
    )


def a_summarised_box(
    id: str, centre: Vec3Tuple, half: Vec3Tuple, up_axis: UpAxis = "+z"
) -> ObjectSummary:
    return summarize(id, "box", a_box(centre, half), frame="map", up_axis=up_axis)


# --- matchers --------------------------------------------------------------------------------


def vec3(values: Sequence[float] | NDArray[np.floating[Any]]) -> Vec3Tuple:
    x, y, z = (float(v) for v in np.asarray(values, dtype=np.float64))
    return (x, y, z)


def is_within(actual: Vec3Tuple, expected: Vec3Tuple, metres: float) -> bool:
    return all(abs(a - e) <= metres for a, e in zip(actual, expected, strict=True))


def spans(lo: Vec3Tuple, hi: Vec3Tuple, expected_lo: Vec3Tuple, expected_hi: Vec3Tuple) -> bool:
    """Whether a min/max pair is the expected box, to a tenth of a millimetre."""
    return is_within(lo, expected_lo, metres=1e-4) and is_within(hi, expected_hi, metres=1e-4)


def yaw_of_longest_axis_deg(obb: Obb) -> float:
    """The heading of the box's first (longest) axis about +z, folded into [0, 180)."""
    x, y = obb.rotation[0][0], obb.rotation[1][0]
    return math.degrees(math.atan2(y, x)) % 180.0


def v_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("v ")]


def f_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("f ")]


def farthest_from(decoded: NDArray[np.float64], cloud: NDArray[np.float32]) -> float:
    """The largest distance from a decoded point to its nearest point in the cloud."""
    origin = cloud.astype(np.float64).mean(axis=0)
    a, b = decoded - origin, cloud.astype(np.float64) - origin
    squared = (a * a).sum(axis=1)[:, None] + (b * b).sum(axis=1)[None, :] - 2.0 * a @ b.T
    return float(math.sqrt(max(float(np.max(squared.min(axis=1))), 0.0)))


def relations(found: tuple[Neighbour, ...]) -> list[Relation]:
    return [n.relation for n in found]


def ids(found: tuple[Neighbour, ...]) -> list[str]:
    return [n.id for n in found]
