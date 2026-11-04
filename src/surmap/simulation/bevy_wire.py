"""Browser-to-bridge wire format for the Bevy stereo stream.

Every message is a little-endian ``u32`` header length, a compact JSON
header, then (pairs only) the left and right grey8 payloads. A fleet page
names the scenario in its ``hello`` and labels each ``pair`` with the drone
whose eyes rendered it; without them the message is the single-drone wire.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass

from surmap.simulation.camera_profile import CameraProfile, parse_camera_profile
from surmap.types import Pose, Vec3


class BevyWireError(ValueError):
    """A message that does not follow the Bevy wire format."""


@dataclass(frozen=True)
class GroundTruthBox:
    id: str
    kind: str
    min_enu: Vec3
    max_enu: Vec3


@dataclass(frozen=True)
class BevyHello:
    camera: CameraProfile
    objects: tuple[GroundTruthBox, ...]
    scenario: str | None = None
    """The scenario a fleet page runs; `None` from a page without one."""


@dataclass(frozen=True)
class BevyPair:
    frame_id: int
    t_ns: int
    width: int
    height: int
    encoding: str
    pose_enu: Pose
    left_data: bytes
    right_data: bytes
    drone_id: str | None = None
    """The fleet drone whose eyes rendered the pair; `None` without a fleet."""


@dataclass(frozen=True)
class FrameKeypoints:
    """One frame's odometry as the page draws it: the pair it sent as `frame_id`, and the
    keypoints RTAB-Map tracked in it as (u, v, depth m), raw left-camera pixels in the frame."""

    frame_id: int
    keypoints: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class DetectedObject:
    """One object the on-board model found: its class, score, box (x0, y0, x1, y1) in raw
    left-camera pixels, and its tracker's id."""

    label: str
    score: float
    box_xyxy: tuple[float, float, float, float]
    track_id: int


@dataclass(frozen=True)
class FrameDetections:
    """What the on-board model found on the pair the page sent as `frame_id`."""

    frame_id: int
    objects: tuple[DetectedObject, ...]


@dataclass(frozen=True)
class BridgeStatus:
    frames: int
    posed: int
    lost: bool
    keyframes: int
    dropped: int
    drone_id: str | None = None
    """The drone whose map the status describes; absent for a pair without a drone id."""
    error: str | None = None
    """Why the pair was not processed (e.g. the drone session limit)."""
    odometry: tuple[FrameKeypoints, ...] = ()
    """The odometry that came back while this pair was handled, oldest first: usually an
    earlier pair's, as RTAB-Map answers asynchronously."""
    detections: tuple[FrameDetections, ...] = ()
    """What the on-board model the agent chose found on this pair; empty without one."""


def encode_status(status: BridgeStatus) -> str:
    """The status text message; `drone_id`, `error`, `odometry` and `detections` appear only
    when set."""
    body: dict[str, object] = {
        "type": "status",
        "frames": status.frames,
        "posed": status.posed,
        "lost": status.lost,
        "keyframes": status.keyframes,
        "dropped": status.dropped,
    }
    if status.drone_id is not None:
        body["drone_id"] = status.drone_id
    if status.error is not None:
        body["error"] = status.error
    if status.odometry:
        body["odometry"] = [
            {"frame_id": frame.frame_id, "keypoints": [list(k) for k in frame.keypoints]}
            for frame in status.odometry
        ]
    if status.detections:
        body["detections"] = [
            {
                "frame_id": frame.frame_id,
                "objects": [
                    {
                        "label": found.label,
                        "score": found.score,
                        "box": list(found.box_xyxy),
                        "track_id": found.track_id,
                    }
                    for found in frame.objects
                ],
            }
            for frame in status.detections
        ]
    return json.dumps(body, separators=(",", ":"))


def _obj(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise BevyWireError(f"{what} must be a JSON object")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise BevyWireError(f"{what} keys must be strings")
        result[key] = item
    return result


def _req(obj: dict[str, object], key: str) -> object:
    if key not in obj:
        raise BevyWireError(f"missing field {key!r}")
    return obj[key]


def _str(obj: dict[str, object], key: str) -> str:
    value = _req(obj, key)
    if not isinstance(value, str):
        raise BevyWireError(f"field {key!r} must be a string")
    return value


def _opt_str(obj: dict[str, object], key: str) -> str | None:
    if key not in obj:
        return None
    return _str(obj, key)


def _int(obj: dict[str, object], key: str) -> int:
    value = _req(obj, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise BevyWireError(f"field {key!r} must be an integer")
    return value


def _float(obj: dict[str, object], key: str) -> float:
    value = _req(obj, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BevyWireError(f"field {key!r} must be a number")
    return float(value)


def _numbers(value: object, count: int, what: str) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != count:
        raise BevyWireError(f"{what} must be {count} numbers")
    out: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise BevyWireError(f"{what} must be {count} numbers")
        out.append(float(item))
    return tuple(out)


def _vec3(value: object, what: str) -> Vec3:
    x, y, z = _numbers(value, 3, what)
    return Vec3(x, y, z)


def decode_bevy_message(message: bytes) -> BevyHello | BevyPair:
    if len(message) < 4:
        raise BevyWireError("message shorter than its header length")
    (header_len,) = struct.unpack_from("<I", message, 0)
    header_end = 4 + header_len
    if len(message) < header_end:
        raise BevyWireError("message shorter than its header length")
    try:
        raw_header: object = json.loads(message[4:header_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BevyWireError(f"header is not JSON: {exc}") from exc
    header = _obj(raw_header, "header")
    kind = _str(header, "type")
    if kind == "hello":
        return _decode_hello(header)
    if kind == "pair":
        return _decode_pair(header, message[header_end:])
    raise BevyWireError(f"unknown message type {kind!r}")


def _decode_hello(header: dict[str, object]) -> BevyHello:
    try:
        camera = parse_camera_profile(_req(header, "camera"))
    except ValueError as exc:
        raise BevyWireError(f"hello camera profile: {exc}") from exc
    raw_objects = _req(header, "objects")
    if not isinstance(raw_objects, list):
        raise BevyWireError("objects must be a list")
    objects: list[GroundTruthBox] = []
    for raw in raw_objects:
        obj = _obj(raw, "ground-truth object")
        objects.append(
            GroundTruthBox(
                id=_str(obj, "id"),
                kind=_str(obj, "kind"),
                min_enu=_vec3(_req(obj, "min_enu"), "min_enu"),
                max_enu=_vec3(_req(obj, "max_enu"), "max_enu"),
            )
        )
    return BevyHello(camera=camera, objects=tuple(objects), scenario=_opt_str(header, "scenario"))


def _decode_pair(header: dict[str, object], payload: bytes) -> BevyPair:
    width = _int(header, "width")
    height = _int(header, "height")
    if width <= 0 or height <= 0:
        raise BevyWireError("pair dimensions must be positive")
    frame_bytes = width * height
    if len(payload) < 2 * frame_bytes:
        raise BevyWireError("pair payload shorter than its frame")
    pose_numbers = _numbers(_req(header, "pose_enu"), 7, "pose_enu")
    pose = Pose(
        Vec3(pose_numbers[0], pose_numbers[1], pose_numbers[2]),
        (pose_numbers[3], pose_numbers[4], pose_numbers[5], pose_numbers[6]),
    )
    return BevyPair(
        frame_id=_int(header, "frame_id"),
        t_ns=_int(header, "t_ns"),
        width=width,
        height=height,
        encoding=_str(header, "encoding"),
        pose_enu=pose,
        left_data=payload[:frame_bytes],
        right_data=payload[frame_bytes : 2 * frame_bytes],
        drone_id=_opt_str(header, "drone_id"),
    )
