"""Pure helpers for the ROS 2 SITL capture dumper.

The dumper itself (`scripts/ros2/dump_sitl_capture.py`) runs under a
ROS-sourced interpreter. These functions stay free of rclpy so the
capture rules can be tested with the rest of SurMap.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from PIL import Image

_T = TypeVar("_T")


class _ImageMessage(Protocol):
    """The `sensor_msgs/Image` fields the dumper reads."""

    encoding: str
    width: int
    height: int
    step: int
    data: bytes


def navsat_accuracy_m(variance_m2: float) -> float:
    """Horizontal accuracy in metres from a NavSatFix variance (m²).

    `sensor_msgs/NavSatFix.position_covariance` is in metres squared.
    A non-positive or non-finite variance (the common all-zero report)
    falls back to 1 m.
    """
    if not math.isfinite(variance_m2) or variance_m2 <= 0.0:
        return 1.0
    return math.sqrt(variance_m2)


def take_stereo_pair(
    left: dict[int, _T],
    right: dict[int, _T],
    *,
    slop_ns: int,
) -> tuple[int, _T, _T] | None:
    """Pair one left stamp with the closest right stamp inside `slop_ns`.

    The pair is removed from both buffers. Any stamp still buffered and
    older than twice the slop, measured from the newest stamp still
    present, is dropped. A one-sided stream therefore cannot grow
    without bound, and a frame that arrives up to one slop late can
    still pair.
    """
    pair: tuple[int, _T, _T] | None = None
    if left and right:
        for left_stamp in list(left):
            right_stamp = min(right, key=lambda stamp: abs(stamp - left_stamp))
            if abs(right_stamp - left_stamp) > slop_ns:
                continue
            pair = (left_stamp, left.pop(left_stamp), right.pop(right_stamp))
            break
    _drop_stale_frames(left, right, slop_ns=slop_ns)
    return pair


def image_msg_to_png(msg: _ImageMessage, target: Path) -> None:
    """Write a `sensor_msgs/Image` to PNG without cv_bridge.

    `step` is the row stride in bytes. When it is wider than the packed
    pixels, the padding at the end of each row is dropped. A zero step
    means the buffer is already packed.
    """
    encoding = str(msg.encoding).lower()
    width = int(msg.width)
    height = int(msg.height)
    data = bytes(msg.data)
    if encoding in ("rgb8", "bgr8"):
        channels = 3
        mode = "RGB"
    elif encoding in ("mono8", "8uc1"):
        channels = 1
        mode = "L"
    else:
        raise ValueError(f"unsupported image encoding {encoding!r} (use rgb8/bgr8/mono8)")
    step = int(getattr(msg, "step", 0) or 0)
    packed = _pack_rows(data, width=width, height=height, channels=channels, step=step)
    image = Image.frombytes(mode, (width, height), packed)
    if encoding == "bgr8":
        red, green, blue = image.split()
        image = Image.merge("RGB", (blue, green, red))
    image.save(target, format="PNG")


def _pack_rows(data: bytes, *, width: int, height: int, channels: int, step: int) -> bytes:
    row_bytes = width * channels
    if step == 0 or step == row_bytes:
        return data
    if step < row_bytes:
        raise ValueError(f"image step {step} is shorter than a packed row ({row_bytes})")
    if len(data) < step * height:
        raise ValueError(
            f"image data has {len(data)} bytes, expected at least {step * height} for step {step}"
        )
    return b"".join(data[row * step : row * step + row_bytes] for row in range(height))


@dataclass(frozen=True)
class StampedPose:
    """Ground-truth camera pose: translation in metres plus quaternion (x, y, z, w)."""

    t_ns: int
    x_m: float
    y_m: float
    z_m: float
    orientation_xyzw: tuple[float, float, float, float]
    frame: str = "gazebo_enu"


def nearest_stamp(stamps: Sequence[int], t_ns: int, *, slop_ns: int) -> int | None:
    """Closest stamp within `slop_ns`, or None."""
    if not stamps:
        return None
    chosen = min(stamps, key=lambda stamp: (abs(stamp - t_ns), stamp))
    if abs(chosen - t_ns) > slop_ns:
        return None
    return chosen


def nearest_pose(
    poses: Sequence[StampedPose],
    t_ns: int,
    *,
    slop_ns: int,
) -> StampedPose | None:
    """Pose whose stamp is closest to `t_ns` and inside the slop."""
    chosen = nearest_stamp(tuple(pose.t_ns for pose in poses), t_ns, slop_ns=slop_ns)
    if chosen is None:
        return None
    for pose in poses:
        if pose.t_ns == chosen:
            return pose
    return None


def pose_record(pose: StampedPose) -> dict[str, object]:
    """JSON object stored on a capture frame and in poses.jsonl."""
    return {
        "t_ns": pose.t_ns,
        "position_m": {"x": pose.x_m, "y": pose.y_m, "z": pose.z_m},
        "orientation_xyzw": list(pose.orientation_xyzw),
        "frame": pose.frame,
    }


def load_pose_jsonl(path: Path) -> tuple[StampedPose, ...]:
    """Read poses written by the SITL dumper."""
    import json

    poses: list[StampedPose] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        raw = json.loads(text)
        if not isinstance(raw, dict):
            raise ValueError(f"poses.jsonl line {line_no} must be an object")
        body = {str(key): value for key, value in raw.items()}
        position = body.get("position_m")
        quaternion = body.get("orientation_xyzw")
        if (
            not isinstance(position, dict)
            or not isinstance(quaternion, list)
            or len(quaternion) != 4
        ):
            raise ValueError(f"poses.jsonl line {line_no} is missing a pose")
        point = {str(key): value for key, value in position.items()}
        poses.append(
            StampedPose(
                t_ns=int(body["t_ns"]),
                x_m=float(point["x"]),
                y_m=float(point["y"]),
                z_m=float(point["z"]),
                orientation_xyzw=(
                    float(quaternion[0]),
                    float(quaternion[1]),
                    float(quaternion[2]),
                    float(quaternion[3]),
                ),
                frame=str(body.get("frame", "gazebo_enu")),
            )
        )
    return tuple(poses)


def label_image_to_png(msg: _ImageMessage, target: Path) -> None:
    """Write a segmentation image. 16-bit labels stay 16-bit; colour stays PNG."""
    encoding = str(msg.encoding).lower()
    if encoding in ("mono16", "16uc1"):
        _write_mono16(msg, target)
        return
    image_msg_to_png(msg, target)


def _write_mono16(msg: _ImageMessage, target: Path) -> None:
    width = int(msg.width)
    height = int(msg.height)
    step = int(msg.step or 0)
    packed = _pack_rows(bytes(msg.data), width=width, height=height, channels=2, step=step)
    expected = width * height * 2
    if len(packed) != expected:
        raise ValueError(f"mono16 image has {len(packed)} bytes, expected {expected}")
    image = Image.frombytes("I;16", (width, height), packed)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="PNG")


def _drop_stale_frames(
    left: dict[int, _T],
    right: dict[int, _T],
    *,
    slop_ns: int,
) -> None:
    stamps = (*left, *right)
    if not stamps:
        return
    cutoff = max(stamps) - 2 * slop_ns
    for buf in (left, right):
        for stamp in [stamp for stamp in buf if stamp < cutoff]:
            del buf[stamp]
