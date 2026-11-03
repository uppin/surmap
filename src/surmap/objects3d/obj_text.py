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

import re
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from surmap.objects3d.summary import ObjectSummary, UpAxis

_MAGIC = "# surmap-obj v1"
_UP_AXES: dict[str, UpAxis] = {"+y": "+y", "-y": "-y", "+z": "+z"}
_DECIMATED = re.compile(r"\(decimated from (\d+)\)")


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
    cloud = np.asarray(points, dtype=np.float64)
    if cloud.ndim != 2 or cloud.shape[1] != 3 or len(cloud) == 0:
        raise ValueError(f"points must be a non-empty Nx3 set, got shape {cloud.shape}")
    if limits.max_points < 1:
        raise ValueError("max_points must be at least 1")

    origin = np.round(np.asarray(summary.obb.centre, dtype=np.float64), 2)
    kept = _downsample(cloud, limits)
    kept_mask = np.zeros(len(cloud), dtype=bool)
    kept_mask[kept] = True
    new_index = np.cumsum(kept_mask) - 1

    face_rows = np.empty((0, 3), dtype=np.int64)
    if faces is not None:
        old = np.asarray(faces, dtype=np.int64)
        survived = old[kept_mask[old].all(axis=1)]
        face_rows = (new_index[survived] + 1)[: limits.max_faces]

    vertices = np.rint((cloud[kept] - origin) * 100.0).astype(np.int64)
    decimated = f" (decimated from {len(cloud)})" if len(kept) != len(cloud) else ""
    lines = [
        f"{_MAGIC} id={_token(summary.id)} label={_token(summary.label)} "
        f"frame={_token(summary.frame)} up={summary.up_axis} unit=cm",
        f"# origin_m={origin[0]:.2f},{origin[1]:.2f},{origin[2]:.2f} scale=0.01 "
        f"points={len(kept)}{decimated}",
    ]
    for row, source in enumerate(kept):
        x, y, z = (int(v) for v in vertices[row])
        vertex = f"v {x} {y} {z}"
        if colors is not None:
            r, g, b = (int(c) for c in colors[source])
            vertex += f" {r} {g} {b}"
        lines.append(vertex)
    lines.extend(f"f {a} {b} {c}" for a, b, c in face_rows.tolist())
    return "\n".join(lines) + "\n"


def decode_obj_text(text: str) -> DecodedObj:
    """Read a `surmap-obj v1` block; raises `ValueError` when it is not one."""
    lines = text.splitlines()
    if len(lines) < 2 or not lines[0].startswith(_MAGIC):
        raise ValueError("not a surmap-obj v1 block")

    head = _fields(lines[0].removeprefix(_MAGIC))
    if head.get("unit") != "cm":
        raise ValueError("surmap-obj v1 blocks are in centimetres")
    up_axis = _UP_AXES.get(_need(head, "up"))
    if up_axis is None:
        raise ValueError(f"unknown up axis: {head['up']!r}")

    match = _DECIMATED.search(lines[1])
    origin_line = _fields(_DECIMATED.sub("", lines[1]).removeprefix("#"))
    origin_parts = _need(origin_line, "origin_m").split(",")
    if len(origin_parts) != 3:
        raise ValueError("origin_m must name three coordinates")
    origin = (float(origin_parts[0]), float(origin_parts[1]), float(origin_parts[2]))
    scale = float(_need(origin_line, "scale"))

    vertex_rows: list[list[int]] = []
    face_rows: list[list[int]] = []
    for line in lines[2:]:
        kind, *rest = line.split()
        if kind == "v":
            vertex_rows.append([int(value) for value in rest])
        elif kind == "f":
            face_rows.append([int(value) - 1 for value in rest])
        else:
            raise ValueError(f"unexpected line in surmap-obj block: {line!r}")

    widths = {len(row) for row in vertex_rows}
    if not widths <= {3} and not widths <= {6}:
        raise ValueError("vertex lines must all carry xyz, or all carry xyz and rgb")
    coords = np.asarray([row[:3] for row in vertex_rows], dtype=np.float64).reshape(-1, 3)
    colors = None
    if widths == {6}:
        colors = np.asarray([row[3:] for row in vertex_rows], dtype=np.uint8)
    if any(len(row) != 3 for row in face_rows):
        raise ValueError("face lines must name exactly three vertices")
    faces = None
    if face_rows:
        faces = np.asarray(face_rows, dtype=np.int32).reshape(-1, 3)

    return DecodedObj(
        id=_need(head, "id"),
        label=_need(head, "label"),
        frame=_need(head, "frame"),
        up_axis=up_axis,
        origin_m=origin,
        scale=scale,
        decimated_from=int(match.group(1)) if match else None,
        points=np.asarray(origin, dtype=np.float64) + coords * scale,
        colors=colors,
        faces=faces,
    )


def _downsample(cloud: NDArray[np.float64], limits: ObjTextLimits) -> NDArray[np.intp]:
    """Indices of one point per voxel (the first in input order), capped evenly."""
    voxels = np.floor(cloud / limits.voxel_m).astype(np.int64)
    _, first = np.unique(voxels, axis=0, return_index=True)
    kept = np.sort(first)
    if len(kept) > limits.max_points:
        pick = np.linspace(0, len(kept) - 1, limits.max_points).round().astype(np.intp)
        kept = kept[pick]
    return kept.astype(np.intp)


def _token(value: str) -> str:
    return re.sub(r"\s+", "_", value)


def _fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in text.split():
        key, sep, value = token.partition("=")
        if sep:
            out[key] = value
    return out


def _need(fields: dict[str, str], key: str) -> str:
    if key not in fields:
        raise ValueError(f"surmap-obj v1 header is missing {key}=")
    return fields[key]
