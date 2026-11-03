"""A dependency-free GLB (binary glTF 2.0) writer for one object's geometry.

One mesh, one primitive: mode 0 (POINTS) for a point set, mode 4 (TRIANGLES) when faces are
given. `POSITION` is float32 in the object frame's metres, with accessor min/max equal to the
AABB; `COLOR_0` is optional. `asset.extras` carries `frame` and `up_axis`.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from surmap.objects3d.summary import UpAxis

_GLB_VERSION = 2
_JSON_CHUNK = 0x4E4F534A
_BIN_CHUNK = 0x004E4942
_POINTS_MODE = 0
_TRIANGLES_MODE = 4
_FLOAT32 = 5126
_UINT32 = 5125
_UBYTE = 5121


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
    cloud = np.ascontiguousarray(points, dtype="<f4")
    if cloud.ndim != 2 or cloud.shape[1] != 3 or len(cloud) == 0:
        raise ValueError(f"points must be a non-empty Nx3 set, got shape {cloud.shape}")

    buffer = _BinaryBuffer()
    accessors: list[dict[str, Any]] = []
    attributes: dict[str, int] = {}

    attributes["POSITION"] = len(accessors)
    accessors.append(
        {
            "bufferView": buffer.add(cloud.tobytes()),
            "componentType": _FLOAT32,
            "count": len(cloud),
            "type": "VEC3",
            "min": [float(v) for v in cloud.min(axis=0)],
            "max": [float(v) for v in cloud.max(axis=0)],
        }
    )

    if colors is not None:
        rgb = np.ascontiguousarray(colors, dtype=np.uint8)
        if rgb.shape != cloud.shape:
            raise ValueError("colors must match the points, one RGB triple each")
        attributes["COLOR_0"] = len(accessors)
        accessors.append(
            {
                "bufferView": buffer.add(rgb.tobytes()),
                "componentType": _UBYTE,
                "normalized": True,
                "count": len(rgb),
                "type": "VEC3",
            }
        )

    primitive: dict[str, Any] = {"attributes": attributes, "mode": _POINTS_MODE}
    if faces is not None:
        tris = np.ascontiguousarray(faces, dtype="<u4")
        if tris.ndim != 2 or tris.shape[1] != 3:
            raise ValueError(f"faces must be Mx3, got shape {tris.shape}")
        if tris.size and int(tris.max()) >= len(cloud):
            raise ValueError("a face names a vertex that is not in the point set")
        primitive["mode"] = _TRIANGLES_MODE
        primitive["indices"] = len(accessors)
        accessors.append(
            {
                "bufferView": buffer.add(tris.tobytes()),
                "componentType": _UINT32,
                "count": tris.size,
                "type": "SCALAR",
            }
        )

    document: dict[str, Any] = {
        "asset": {
            "version": "2.0",
            "generator": "surmap",
            "extras": {"frame": frame, "up_axis": up_axis},
        },
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [primitive]}],
        "accessors": accessors,
        "bufferViews": buffer.views,
        "buffers": [{"byteLength": len(buffer.data)}],
    }
    json_chunk = _pad(json.dumps(document, separators=(",", ":")).encode("utf-8"), b" ")
    bin_chunk = buffer.data
    length = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    return (
        struct.pack("<4sII", b"glTF", _GLB_VERSION, length)
        + struct.pack("<II", len(json_chunk), _JSON_CHUNK)
        + json_chunk
        + struct.pack("<II", len(bin_chunk), _BIN_CHUNK)
        + bin_chunk
    )


def read_glb_header(data: bytes) -> GlbHeader:
    """Parse a GLB's 12-byte header, its JSON chunk and its BIN chunk length."""
    if len(data) < 20:
        raise ValueError("too short to be a GLB")
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError("not a GLB file")
    json_length, json_type = struct.unpack_from("<II", data, 12)
    if json_type != _JSON_CHUNK or len(data) < 20 + json_length + 8:
        raise ValueError("GLB must open with a JSON chunk followed by a BIN chunk")
    document: dict[str, Any] = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    bin_length, bin_type = struct.unpack_from("<II", data, 20 + json_length)
    if bin_type != _BIN_CHUNK:
        raise ValueError("GLB second chunk is not BIN")

    primitives = [p for mesh in document["meshes"] for p in mesh["primitives"]]
    first = primitives[0]["attributes"]["POSITION"]
    position = document["accessors"][first]
    return GlbHeader(
        magic=magic,
        version=version,
        length=length,
        primitive_modes=tuple(int(p.get("mode", _TRIANGLES_MODE)) for p in primitives),
        position_min=_triple(position["min"]),
        position_max=_triple(position["max"]),
        asset_extras={str(k): str(v) for k, v in document["asset"].get("extras", {}).items()},
        bin_chunk_length=bin_length,
    )


class _BinaryBuffer:
    """Packs byte blobs into one BIN chunk, each padded to 4 bytes, and records their views."""

    def __init__(self) -> None:
        self.data = b""
        self.views: list[dict[str, Any]] = []

    def add(self, blob: bytes) -> int:
        self.views.append({"buffer": 0, "byteOffset": len(self.data), "byteLength": len(blob)})
        self.data += _pad(blob, b"\0")
        return len(self.views) - 1


def _pad(blob: bytes, filler: bytes) -> bytes:
    return blob + filler * (-len(blob) % 4)


def _triple(values: Any) -> tuple[float, float, float]:
    x, y, z = (float(v) for v in values)
    return (x, y, z)
