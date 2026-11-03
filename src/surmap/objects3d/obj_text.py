"""`surmap-obj v1`: OBJ-style text of an object's geometry for an LLM's context.

```text
# surmap-obj v1 id=obj_17 label=car frame=map up=-y unit=cm
# origin_m=412.35,-88.10,2.04 scale=0.01 points=500 (decimated from 14211)
v -226 -90 -74 158 156 153
f 1 2 3
```

`v` lines are integer centimetres relative to `origin_m` (the OBB centre), with an optional
`r g b`; `f` lines are 1-based vertex indices.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from surmap.objects3d.summary import ObjectSummary, UpAxis


@dataclass(frozen=True)
class ObjTextLimits:
    """How much geometry one text block may carry."""

    voxel_m: float = 0.05
    max_points: int = 500
    max_faces: int = 1000


DEFAULT_LIMITS = ObjTextLimits()


@dataclass(frozen=True)
class DecodedObj:
    """A `surmap-obj v1` block read back; `points` in `frame` metres, `faces` 0-based."""

    id: str
    label: str
    frame: str
    up_axis: UpAxis
    origin_m: tuple[float, float, float]
    scale: float
    decimated_from: int | None
    points: NDArray[np.float64]
    colors: NDArray[np.uint8] | None
    faces: NDArray[np.int32] | None


def encode_obj_text(
    summary: ObjectSummary,
    points: NDArray[np.float32],
    *,
    faces: NDArray[np.int32] | None = None,
    colors: NDArray[np.uint8] | None = None,
    limits: ObjTextLimits = DEFAULT_LIMITS,
) -> str:
    """Encode `points` (Nx3, `summary.frame` metres) as a `surmap-obj v1` block.

    Points are voxel-downsampled at `limits.voxel_m`, then capped at `limits.max_points`
    by a deterministic pick; the header then says `(decimated from N)`.
    """
    raise NotImplementedError  # TODO(pr-3): implement


def decode_obj_text(text: str) -> DecodedObj:
    """Read a `surmap-obj v1` block; raises `ValueError` when it is not one."""
    raise NotImplementedError  # TODO(pr-3): implement
