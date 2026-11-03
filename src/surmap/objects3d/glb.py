"""A dependency-free GLB (binary glTF 2.0) writer for one object's geometry.

One mesh, one primitive: mode 0 (POINTS) for a point set, mode 4 (TRIANGLES) when faces are
given. `POSITION` is float32 in the object frame's metres, with accessor min/max equal to the
AABB; `COLOR_0` is optional. `asset.extras` carries `frame` and `up_axis`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from surmap.objects3d.summary import UpAxis


@dataclass(frozen=True)
class GlbHeader:
    """What a GLB's container and JSON chunk say, for checking a file's layout."""

    magic: bytes
    version: int
    length: int
    primitive_modes: tuple[int, ...]
    position_min: tuple[float, float, float]
    position_max: tuple[float, float, float]
    asset_extras: dict[str, str]
    bin_chunk_length: int


def write_glb(
    points: NDArray[np.float32],
    *,
    colors: NDArray[np.uint8] | None = None,
    faces: NDArray[np.int32] | None = None,
    frame: str,
    up_axis: UpAxis,
) -> bytes:
    """Write `points` (Nx3) — and `faces` (Mx3, 0-based) when given — as a GLB."""
    raise NotImplementedError  # TODO(pr-3): implement


def read_glb_header(data: bytes) -> GlbHeader:
    """Parse a GLB's 12-byte header, its JSON chunk and its BIN chunk length."""
    raise NotImplementedError  # TODO(pr-3): implement
