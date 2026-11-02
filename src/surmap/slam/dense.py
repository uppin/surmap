"""RTAB-Map's dense buffer, journalled: region answers without the sidecar.

The streaming sidecar answers a region (`surmap.slam.regions`) from a
ring of recent frames: on a frame's first query it runs dense stereo
(SGBM) once over the whole frame of that channel and keeps the
disparity. With the dense journal on, it also emits that disparity — a
`DenseFrame`, together with the map transform it placed points with —
and announces the `RegionRig` it answers with.

That journalled disparity is the source of truth for replays: nothing
here recomputes stereo. `dense_region_points` repeats only the sidecar's
geometry (deploy/rtabmap-stream/main.cpp `answerRegion`): the polygon
from requester pixels to raw pixels to rectified pixels (OpenCV's
iterative `undistortPoints`), rasterised, back-projected with
`z = fx * b / d` up to the depth cap, and placed in the map frame.
The raster is PIL's rather than `cv::fillPoly`, so an edge pixel can
differ. Points stay a read-only layer on RTAB-Map's output
(docs/architecture.md section 1).
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus, invalid_reason
from surmap.types import Pose, Vec3

# SGBM disparities are fixed-point, 16 units per pixel.
DISPARITY_SUBPIXELS = 16

# OpenCV's default for undistortPoints: 5 fixed-point iterations.
_UNDISTORT_ITERATIONS = 5


@dataclass(frozen=True)
class ChannelRig:
    """One channel's rectification, as OpenCV's stereoRectify gave it.

    `camera_matrix` (K) and `rotation` (R) are 3x3 row-major,
    `projection` (P) is 3x4 row-major, and `distortion` is OpenCV's
    (k1, k2, p1, p2[, k3[, k4, k5, k6]]) of the raw camera.
    """

    camera_matrix: tuple[float, ...]
    distortion: tuple[float, ...]
    rotation: tuple[float, ...]
    projection: tuple[float, ...]


@dataclass(frozen=True)
class RegionRig:
    """What the sidecar answers regions with: raw size, baseline, depth cap, both channels."""

    width: int
    height: int
    baseline_m: float
    max_depth_m: float
    channels: tuple[ChannelRig, ChannelRig]

    def as_message(self) -> dict[str, object]:
        """The rig in its wire shape (the `ready` line's `region_rig`)."""
        return {
            "size": [self.width, self.height],
            "baseline": self.baseline_m,
            "max_depth_m": self.max_depth_m,
            "channels": [
                {
                    "K": list(channel.camera_matrix),
                    "D": list(channel.distortion),
                    "R": list(channel.rotation),
                    "P": list(channel.projection),
                }
                for channel in self.channels
            ],
        }


def _floats(value: object, count: int | None, what: str) -> tuple[float, ...]:
    if not isinstance(value, list) or (count is not None and len(value) != count):
        raise ValueError(f"{what} must be {count or 'a list of'} numbers, got {value!r}")
    try:
        numbers = tuple(float(v) for v in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} is not numeric: {value!r}") from exc
    if not all(np.isfinite(numbers)):
        raise ValueError(f"{what} has non-finite values")
    return numbers


def region_rig_from_message(value: object) -> RegionRig:
    """The rig from its wire shape; ValueError when malformed."""
    if not isinstance(value, dict):
        raise ValueError(f"region_rig must be an object, got {value!r}")
    width, height = _floats(value.get("size"), 2, "region_rig size")
    (baseline,) = _floats([value.get("baseline")], 1, "region_rig baseline")
    (max_depth,) = _floats([value.get("max_depth_m")], 1, "region_rig max_depth_m")
    channels_raw = value.get("channels")
    if not isinstance(channels_raw, list) or len(channels_raw) != 2:
        raise ValueError("region_rig needs exactly two channels")
    channels: list[ChannelRig] = []
    for raw in channels_raw:
        if not isinstance(raw, dict):
            raise ValueError(f"region_rig channel must be an object, got {raw!r}")
        distortion = _floats(raw.get("D"), None, "region_rig D")
        if len(distortion) not in (4, 5, 8):
            raise ValueError(f"region_rig D must have 4, 5 or 8 coefficients, got {distortion}")
        channels.append(
            ChannelRig(
                camera_matrix=_floats(raw.get("K"), 9, "region_rig K"),
                distortion=distortion,
                rotation=_floats(raw.get("R"), 9, "region_rig R"),
                projection=_floats(raw.get("P"), 12, "region_rig P"),
            )
        )
    return RegionRig(int(width), int(height), baseline, max_depth, (channels[0], channels[1]))


@dataclass(frozen=True)
class DenseFrame:
    """One frame's journalled dense buffer for one channel.

    `disparity_png` is the sidecar's SGBM disparity at the rig's size,
    16-bit greyscale PNG in 1/16 px (0 where nothing matched);
    `to_map` is the camera-to-map transform the sidecar placed this
    frame's region points with.
    """

    frame_id: int
    t_ns: int
    channel: int
    to_map: Pose
    disparity_png: bytes


def encode_disparity(disparity: NDArray[np.uint16]) -> bytes:
    """A fixed-point disparity as a lossless 16-bit PNG (the sidecar's encoding)."""
    buffer = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(disparity, dtype=np.uint16)).save(buffer, format="PNG")
    return buffer.getvalue()


def decode_disparity(png: bytes) -> NDArray[np.uint16]:
    with Image.open(io.BytesIO(png)) as image:
        decoded: NDArray[np.uint16] = np.asarray(image, dtype=np.uint16)
    return decoded


def undistort_points(pixels: NDArray[np.float64], channel: ChannelRig) -> NDArray[np.float64]:
    """Raw pixels (N, 2) to rectified pixels: OpenCV's `undistortPoints(K, D, R, P)`."""
    k = np.array(channel.camera_matrix, np.float64).reshape(3, 3)
    coefficients = np.zeros(8, np.float64)
    coefficients[: len(channel.distortion)] = channel.distortion
    k1, k2, p1, p2, k3, k4, k5, k6 = coefficients.tolist()
    x0 = (pixels[:, 0] - k[0, 2]) / k[0, 0]
    y0 = (pixels[:, 1] - k[1, 2]) / k[1, 1]
    x, y = x0.copy(), y0.copy()
    for _ in range(_UNDISTORT_ITERATIONS):
        r2 = x * x + y * y
        inverse = (1 + ((k6 * r2 + k5) * r2 + k4) * r2) / (1 + ((k3 * r2 + k2) * r2 + k1) * r2)
        delta_x = 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
        delta_y = p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
        x, y = (x0 - delta_x) * inverse, (y0 - delta_y) * inverse
    rectify = np.array(channel.projection, np.float64).reshape(3, 4)[:, :3] @ np.array(
        channel.rotation, np.float64
    ).reshape(3, 3)
    homogeneous = np.stack([x, y, np.ones_like(x)], axis=1) @ rectify.T
    rectified: NDArray[np.float64] = homogeneous[:, :2] / homogeneous[:, 2:3]
    return rectified


def _polygon_mask(outline: NDArray[np.int64], width: int, height: int) -> NDArray[np.bool_]:
    """The filled polygon, its edges included (as `cv::fillPoly` fills them)."""
    image = Image.new("L", (width, height), 0)
    vertices = [(int(u), int(v)) for u, v in outline.tolist()]
    ImageDraw.Draw(image).polygon(vertices, fill=255, outline=255)
    mask: NDArray[np.bool_] = np.asarray(image) > 0
    return mask


def _rotation(pose: Pose) -> NDArray[np.float64]:
    x, y, z, w = pose.orientation_xyzw
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def dense_region_points(
    query: RegionQuery, rig: RegionRig, frame: DenseFrame | None
) -> RegionResult:
    """Every journalled dense point inside `query`'s polygon, in the map frame."""

    def answer(status: RegionStatus, points: tuple[Vec3, ...] = ()) -> RegionResult:
        return RegionResult(query.query_id, query.frame_id, query.channel, status, points)

    if invalid_reason(query) is not None:
        return answer(RegionStatus.INVALID_QUERY)
    if frame is None or (frame.frame_id, frame.channel) != (query.frame_id, query.channel):
        return answer(RegionStatus.FRAME_EXPIRED)
    channel = rig.channels[query.channel]
    raw = np.array(query.polygon, np.float64) * (
        rig.width / query.width,
        rig.height / query.height,
    )
    outline = np.rint(undistort_points(raw, channel)).astype(np.int64)
    disparity = decode_disparity(frame.disparity_png)
    inside = _polygon_mask(outline, rig.width, rig.height) & (disparity > 0)
    v, u = np.nonzero(inside)
    projection = np.array(channel.projection, np.float64).reshape(3, 4)
    fx, fy, cx, cy = projection[0, 0], projection[1, 1], projection[0, 2], projection[1, 2]
    depth = fx * rig.baseline_m / (disparity[v, u].astype(np.float64) / DISPARITY_SUBPIXELS)
    kept = (depth > 0) & (depth <= rig.max_depth_m)
    u, v, depth = u[kept], v[kept], depth[kept]
    # The right rectified camera sits +baseline along x of the left one,
    # whose frame is the pose's camera frame.
    offset_x = rig.baseline_m if query.channel == 1 else 0.0
    in_camera = np.stack([(u - cx) * depth / fx + offset_x, (v - cy) * depth / fy, depth], axis=1)
    position = frame.to_map.position
    placed = in_camera @ _rotation(frame.to_map).T + (position.x, position.y, position.z)
    rounded = np.round(placed, 4).tolist()
    return answer(RegionStatus.OK, tuple(Vec3(x, y, z) for x, y, z in rounded))


class DenseBufferRegionSource:
    """`RegionPointSource` over journalled dense frames; a frame it lacks has expired."""

    def __init__(self, rig: RegionRig, frames: Iterable[DenseFrame]) -> None:
        self._rig = rig
        self._frames = {(frame.frame_id, frame.channel): frame for frame in frames}

    def region_points(self, query: RegionQuery, timeout: float = 5.0) -> RegionResult:
        frame = self._frames.get((query.frame_id, query.channel))
        return dense_region_points(query, self._rig, frame)


@runtime_checkable
class DenseJournalSource(Protocol):
    """A live backend that journals its dense buffer (the streaming sidecar, v5)."""

    @property
    def region_rig(self) -> RegionRig | None: ...
    def poll_dense(self) -> list[DenseFrame]: ...
