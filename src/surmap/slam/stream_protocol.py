"""Wire protocol for `surmap-rtabmap-stream` (see PRD §2).

Requests: 4-byte little-endian length + JSON header, followed (for
pairs) by two length-prefixed payloads. Responses: JSON lines.
Pure functions; no `Any` leaves this module.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from typing import TypeAlias

from surmap.types import Pose, Vec3

PROTOCOL_VERSION = 3

# Colour given to a keyframe point the sidecar sent without one.
NEUTRAL_GREY = (160, 160, 160)


class ProtocolError(ValueError):
    """Raised when a peer message is malformed or version-mismatched."""


@dataclass(frozen=True)
class Rectification:
    """The left camera's stereo rectification, at the configured size.

    `rotation` is OpenCV's R1, row-major (rectified = R1 · raw); the
    intrinsics are (fx, fy, cx, cy); `distortion` is radial-tangential
    (k1, k2, p1, p2) of the raw camera.
    """

    rotation: tuple[float, ...]
    rectified: tuple[float, float, float, float]
    raw: tuple[float, float, float, float]
    distortion: tuple[float, float, float, float]


@dataclass(frozen=True)
class Ready:
    version: int
    rectification: Rectification | None = None


@dataclass(frozen=True)
class Keypoint:
    """One feature odometry tracked as an inlier: rectified pixel + depth (m)."""

    word_id: int
    u: float
    v: float
    depth: float


@dataclass(frozen=True)
class OdomUpdate:
    frame_id: int
    t_ns: int
    pose: Pose | None
    lost: bool
    ms: float
    keypoints: tuple[Keypoint, ...] = ()
    # The pose after RTAB-Map's odometry-to-map correction (loop closures).
    map_pose: Pose | None = None


@dataclass(frozen=True)
class KeyframeUpdate:
    node_id: int
    frame_id: int
    t_ns: int
    pose: Pose
    points_local: tuple[Vec3, ...]
    colors: tuple[tuple[int, int, int], ...] = ()


@dataclass(frozen=True)
class GraphUpdate:
    poses: tuple[tuple[int, Pose], ...]
    final: bool


@dataclass(frozen=True)
class ErrorUpdate:
    message: str


MapUpdate: TypeAlias = OdomUpdate | KeyframeUpdate | GraphUpdate
ServerMessage: TypeAlias = Ready | MapUpdate | ErrorUpdate


def _frame(obj: dict[str, object], payload: bytes = b"") -> bytes:
    header = json.dumps(obj, separators=(",", ":")).encode()
    return struct.pack("<I", len(header)) + header + payload


def encode_hello(
    cam0_yaml: str,
    cam1_yaml: str,
    width: int,
    height: int,
    params: dict[str, str],
    max_depth_m: float = 30.0,
    min_disparity_px: float = 2.0,
) -> bytes:
    return _frame(
        {
            "type": "hello",
            "version": PROTOCOL_VERSION,
            "cam0_yaml": cam0_yaml,
            "cam1_yaml": cam1_yaml,
            "width": width,
            "height": height,
            "params": params,
            # Keyframe points beyond this depth are too noisy to map.
            "max_depth_m": max_depth_m,
            # Points with a smaller disparity are dropped as well.
            "min_disparity_px": min_disparity_px,
        }
    )


def encode_pair(
    frame_id: int,
    t_ns: int,
    width: int,
    height: int,
    left: bytes,
    right: bytes,
    encoding: str = "png",
) -> bytes:
    payload = struct.pack("<I", len(left)) + left + struct.pack("<I", len(right)) + right
    return _frame(
        {
            "type": "pair",
            "frame_id": frame_id,
            "t_ns": t_ns,
            "width": width,
            "height": height,
            "encoding": encoding,
        },
        payload,
    )


def _pose(value: object) -> Pose:
    if not isinstance(value, list) or len(value) != 7:
        raise ProtocolError(f"pose must be 7 numbers, got {value!r}")
    try:
        nums = [float(v) for v in value]
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"pose is not numeric: {value!r}") from exc
    if not all(math.isfinite(n) for n in nums):
        raise ProtocolError("pose has non-finite values")
    return Pose(Vec3(nums[0], nums[1], nums[2]), (nums[3], nums[4], nums[5], nums[6]))


def _req(obj: dict[str, object], key: str) -> object:
    if key not in obj:
        raise ProtocolError(f"message missing {key!r}: {obj!r}")
    return obj[key]


def _int(obj: dict[str, object], key: str) -> int:
    value = _req(obj, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"{key} must be an int, got {value!r}")
    return value


def _numbers(value: object, count: int, what: str) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != count:
        raise ProtocolError(f"{what} must be {count} numbers, got {value!r}")
    try:
        nums = tuple(float(v) for v in value)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"{what} is not numeric: {value!r}") from exc
    if not all(math.isfinite(n) for n in nums):
        raise ProtocolError(f"{what} has non-finite values")
    return nums


def _intrinsics(value: object, what: str) -> tuple[float, float, float, float]:
    fx, fy, cx, cy = _numbers(value, 4, what)
    return fx, fy, cx, cy


def _rectification(value: object) -> Rectification:
    if not isinstance(value, dict):
        raise ProtocolError(f"rectification must be an object, got {value!r}")
    obj: dict[str, object] = value
    return Rectification(
        rotation=_numbers(_req(obj, "rotation"), 9, "rotation"),
        rectified=_intrinsics(_req(obj, "rectified"), "rectified"),
        raw=_intrinsics(_req(obj, "raw"), "raw"),
        distortion=_intrinsics(_req(obj, "distortion"), "distortion"),
    )


def _keypoints(value: object) -> tuple[Keypoint, ...]:
    if not isinstance(value, list):
        raise ProtocolError("keypoints must be a list")
    keypoints = []
    for entry in value:
        word_id, u, v, depth = _numbers(entry, 4, "keypoint")
        keypoints.append(Keypoint(int(word_id), u, v, depth))
    return tuple(keypoints)


def decode_server_line(line: str | bytes) -> ServerMessage:
    text = line.decode() if isinstance(line, bytes) else line
    text = text.strip()
    if not text:
        raise ProtocolError("empty server line")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"server line is not JSON: {text[:120]!r}") from exc
    if not isinstance(raw, dict):
        raise ProtocolError("server message must be an object")
    obj: dict[str, object] = raw
    kind = obj.get("type")
    if kind == "ready":
        version = _int(obj, "version")
        if version != PROTOCOL_VERSION:
            raise ProtocolError(
                f"protocol version mismatch: server {version}, client {PROTOCOL_VERSION}"
            )
        rectification = obj.get("rectification")
        return Ready(version, None if rectification is None else _rectification(rectification))
    if kind == "error":
        message = _req(obj, "message")
        return ErrorUpdate(str(message))
    if kind == "odom":
        pose_raw = _req(obj, "pose")
        ms_raw = _req(obj, "ms")
        if isinstance(ms_raw, bool) or not isinstance(ms_raw, (int, float)):
            raise ProtocolError("ms must be a number")
        return OdomUpdate(
            frame_id=_int(obj, "frame_id"),
            t_ns=_int(obj, "t_ns"),
            pose=None if pose_raw is None else _pose(pose_raw),
            lost=bool(_req(obj, "lost")),
            ms=float(ms_raw),
            keypoints=_keypoints(obj.get("keypoints", [])),
            map_pose=None if obj.get("map_pose") is None else _pose(obj["map_pose"]),
        )
    if kind == "keyframe":
        points_raw = _req(obj, "points_local")
        if not isinstance(points_raw, list):
            raise ProtocolError("points_local must be a list")
        points = []
        colors = []
        for entry in points_raw:
            # [x, y, z] or [x, y, z, r, g, b]
            if not isinstance(entry, list) or len(entry) not in (3, 6):
                raise ProtocolError(f"point must be 3 or 6 numbers, got {entry!r}")
            try:
                point = Vec3(float(entry[0]), float(entry[1]), float(entry[2]))
                color = (
                    (int(entry[3]), int(entry[4]), int(entry[5]))
                    if len(entry) == 6
                    else NEUTRAL_GREY
                )
            except (TypeError, ValueError) as exc:
                raise ProtocolError(f"point is not numeric: {entry!r}") from exc
            if all(math.isfinite(c) for c in (point.x, point.y, point.z)):
                points.append(point)
                colors.append(color)
        return KeyframeUpdate(
            node_id=_int(obj, "node_id"),
            frame_id=_int(obj, "frame_id"),
            t_ns=_int(obj, "t_ns"),
            pose=_pose(_req(obj, "pose")),
            points_local=tuple(points),
            colors=tuple(colors),
        )
    if kind == "graph":
        poses_raw = _req(obj, "poses")
        if not isinstance(poses_raw, list):
            raise ProtocolError("poses must be a list")
        poses: list[tuple[int, Pose]] = []
        for entry in poses_raw:
            if not isinstance(entry, dict):
                raise ProtocolError(f"graph pose must be an object, got {entry!r}")
            poses.append((_int(entry, "node_id"), _pose(_req(entry, "pose"))))
        return GraphUpdate(tuple(poses), bool(_req(obj, "final")))
    raise ProtocolError(f"unknown server message type: {kind!r}")
