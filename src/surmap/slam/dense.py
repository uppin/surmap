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
iterative `undistortPoints`), its vertices rounded as `lround` does,
rasterised exactly as `cv::fillPoly` does (`fill_poly`, a port of
OpenCV 4.6), back-projected with `z = fx * b / d` up to the depth cap,
and placed in the map frame. The same pixels therefore give the same
points; only float32 (sidecar) against float64 rounding can move a
coordinate by its last printed digit. Points stay a read-only layer
on RTAB-Map's output (docs/architecture.md section 1).
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray
from PIL import Image

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


def round_half_away(values: NDArray[np.float64]) -> NDArray[np.int64]:
    """C's `lround`: to the nearest integer, halves away from zero."""
    rounded: NDArray[np.int64] = (np.sign(values) * np.floor(np.abs(values) + 0.5)).astype(np.int64)
    return rounded


# OpenCV's fixed point for polygon edges (drawing.cpp XY_SHIFT / XY_ONE).
_XY_SHIFT = 16
_XY_ONE = 1 << _XY_SHIFT


def _trunc_div(a: int, b: int) -> int:
    """C integer division (towards zero), unlike Python's floor division."""
    quotient = abs(a) // abs(b)
    return quotient if (a >= 0) == (b > 0) else -quotient


def _clip_line(
    width: int, height: int, p1: tuple[int, int], p2: tuple[int, int]
) -> tuple[int, int, int, int] | None:
    """OpenCV's `clipLine`: the segment clipped to the image, or None outside it."""
    (x1, y1), (x2, y2) = p1, p2
    right, bottom = width - 1, height - 1

    def code(x: int, y: int) -> int:
        return (x < 0) + (x > right) * 2 + (y < 0) * 4 + (y > bottom) * 8

    c1, c2 = code(x1, y1), code(x2, y2)
    if (c1 & c2) == 0 and (c1 | c2) != 0:
        if c1 & 12:
            a = 0 if c1 < 8 else bottom
            x1 += int(float(a - y1) * (x2 - x1) / (y2 - y1))
            y1 = a
            c1 = (x1 < 0) + (x1 > right) * 2
        if c2 & 12:
            a = 0 if c2 < 8 else bottom
            x2 += int(float(a - y2) * (x2 - x1) / (y2 - y1))
            y2 = a
            c2 = (x2 < 0) + (x2 > right) * 2
        if (c1 & c2) == 0 and (c1 | c2) != 0:
            if c1:
                a = 0 if c1 == 1 else right
                y1 += int(float(a - x1) * (y2 - y1) / (x2 - x1))
                x1 = a
                c1 = 0
            if c2:
                a = 0 if c2 == 1 else right
                y2 += int(float(a - x2) * (y2 - y1) / (x2 - x1))
                x2 = a
                c2 = 0
    return (x1, y1, x2, y2) if (c1 | c2) == 0 else None


def _line8(mask: NDArray[np.bool_], p1: tuple[int, int], p2: tuple[int, int]) -> None:
    """OpenCV's 8-connected `Line` (a left-to-right `LineIterator`)."""
    height, width = mask.shape
    if not (
        0 <= p1[0] < width and 0 <= p2[0] < width and 0 <= p1[1] < height and 0 <= p2[1] < height
    ):
        clipped = _clip_line(width, height, p1, p2)
        if clipped is None:
            return
        p1, p2 = (clipped[0], clipped[1]), (clipped[2], clipped[3])
    delta_x = delta_y = 1
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    if dx < 0:
        dx, dy, p1 = -dx, -dy, p2
    if dy < 0:
        dy, delta_y = -dy, -1
    vertical = dy > dx
    if vertical:
        dx, dy = dy, dx
        delta_x, delta_y = delta_y, delta_x
    err = dx - (dy + dy)
    plus_delta, minus_delta = dx + dx, -(dy + dy)
    # (step in x, step in y) when err >= 0 ("minus") and the extra when err < 0 ("plus")
    minus = (0, delta_x) if vertical else (delta_x, 0)
    plus = (delta_y, 0) if vertical else (0, delta_y)
    x, y = p1
    for _ in range(dx + 1):
        mask[y, x] = True
        if err < 0:
            err += minus_delta + plus_delta
            x, y = x + minus[0] + plus[0], y + minus[1] + plus[1]
        else:
            err += minus_delta
            x, y = x + minus[0], y + minus[1]


class _Edge:
    __slots__ = ("y0", "y1", "x", "dx", "next")

    def __init__(self, y0: int, y1: int, x: int, dx: int) -> None:
        self.y0, self.y1, self.x, self.dx = y0, y1, x, dx
        self.next: _Edge | None = None


def fill_poly(outline: NDArray[np.int64], width: int, height: int) -> NDArray[np.bool_]:
    """The pixels `cv::fillPoly` (8-connected, no shift) covers for one polygon.

    A port of OpenCV 4.6 drawing.cpp `CollectPolyEdges` +
    `FillEdgeCollection`: every edge is drawn as an 8-connected line,
    then spans between active edges are filled scanline by scanline in
    16-bit fixed point.
    """
    mask = np.zeros((height, width), bool)
    vertices = [(int(u), int(v)) for u, v in outline.reshape(-1, 2).tolist()]
    if not vertices:
        return mask
    edges: list[_Edge] = []
    x0, y0 = vertices[-1][0] << _XY_SHIFT, vertices[-1][1]
    for u, v in vertices:
        x1, y1 = u << _XY_SHIFT, v
        _line8(
            mask, ((x0 + (_XY_ONE >> 1)) >> _XY_SHIFT, y0), ((x1 + (_XY_ONE >> 1)) >> _XY_SHIFT, y1)
        )
        if y0 != y1:
            dx = _trunc_div(x1 - x0, y1 - y0)
            edges.append(_Edge(y0, y1, x0, dx) if y0 < y1 else _Edge(y1, y0, x1, dx))
        x0, y0 = x1, y1
    if len(edges) < 2:
        return mask
    y_min = min(edge.y0 for edge in edges)
    y_max = max(edge.y1 for edge in edges)
    ends = [edge.x + (edge.y1 - edge.y0) * edge.dx for edge in edges]
    x_min = min(min(edge.x for edge in edges), min(ends))
    x_max = max(max(edge.x for edge in edges), max(ends))
    if y_max < 0 or y_min >= height or x_max < 0 or x_min >= (width << _XY_SHIFT):
        return mask
    edges.sort(key=lambda edge: (edge.y0, edge.x, edge.dx))
    sentinel = _Edge(2**31 - 1, 0, 0, 0)
    edges.append(sentinel)
    total = len(edges) - 1
    head = _Edge(0, 0, 0, 0)  # `tmp`: the active list hangs off head.next
    i = 0
    e = edges[0]
    y_max = min(y_max, height)
    y = e.y0
    while y < y_max:
        draw = False
        clip = y < 0
        prelast: _Edge = head
        last = head.next
        while last is not None or e.y0 == y:
            if last is not None and last.y1 == y:
                prelast.next = last.next  # an edge leaves at its lower end
                last = last.next
                continue
            keep_prelast = prelast
            if last is not None and (e.y0 > y or last.x < e.x):
                prelast, last = last, last.next
            elif i < total:
                prelast.next = e  # an edge joins at its upper end
                e.next = last
                prelast = e
                i += 1
                e = edges[i]
            else:
                break
            if draw:
                if not clip:
                    if keep_prelast.x > prelast.x:
                        xa = (prelast.x + _XY_ONE - 1) >> _XY_SHIFT
                        xb = keep_prelast.x >> _XY_SHIFT
                    else:
                        xa = (keep_prelast.x + _XY_ONE - 1) >> _XY_SHIFT
                        xb = prelast.x >> _XY_SHIFT
                    if xa < width and xb >= 0:
                        mask[y, max(xa, 0) : min(xb, width - 1) + 1] = True
                keep_prelast.x += keep_prelast.dx
                prelast.x += prelast.dx
            draw = not draw
        # Bubble-sort the active list by x, as OpenCV does.
        keep: _Edge | None = None
        while True:
            prelast = head
            last = head.next
            exchanged: _Edge | None = None
            while last is not keep and last is not None and last.next is not None:
                after = last.next
                if last.x > after.x:
                    prelast.next = after
                    last.next = after.next
                    after.next = last
                    prelast = after
                    exchanged = prelast
                else:
                    prelast, last = last, after
            if exchanged is None:
                break
            keep = exchanged
            if keep is head.next or keep is head:
                break
        y += 1
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
    query: RegionQuery,
    rig: RegionRig,
    frame: DenseFrame | None,
    disparity: NDArray[np.uint16] | None = None,
) -> RegionResult:
    """Every journalled dense point inside `query`'s polygon, in the map frame.

    `disparity`, when given, is `frame`'s already decoded disparity.
    """

    def answer(
        status: RegionStatus, points: tuple[Vec3, ...] = (), camera: Pose | None = None
    ) -> RegionResult:
        return RegionResult(query.query_id, query.frame_id, query.channel, status, points, camera)

    if invalid_reason(query) is not None:
        return answer(RegionStatus.INVALID_QUERY)
    if frame is None or (frame.frame_id, frame.channel) != (query.frame_id, query.channel):
        return answer(RegionStatus.FRAME_EXPIRED)
    channel = rig.channels[query.channel]
    raw = np.array(query.polygon, np.float64) * (
        rig.width / query.width,
        rig.height / query.height,
    )
    outline = round_half_away(undistort_points(raw, channel))
    if disparity is None:
        disparity = decode_disparity(frame.disparity_png)
    inside = fill_poly(outline, rig.width, rig.height) & (disparity > 0)
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
    return answer(
        RegionStatus.OK,
        tuple(Vec3(x, y, z) for x, y, z in rounded),
        channel_camera(frame.to_map, rig, query.channel),
    )


def channel_camera(to_map: Pose, rig: RegionRig, channel: int) -> Pose:
    """The rectified camera of `channel`: the right one sits +baseline along the left's x."""
    if channel == 0:
        return to_map
    x, y, z = (_rotation(to_map) @ np.array([rig.baseline_m, 0.0, 0.0])).tolist()
    position = to_map.position
    return Pose(Vec3(position.x + x, position.y + y, position.z + z), to_map.orientation_xyzw)


def project_to_display(
    points: NDArray[np.float64] | NDArray[np.float32],
    camera: Pose,
    rig: RegionRig,
    channel: int,
    size: tuple[int, int],
) -> NDArray[np.float64]:
    """Map-frame points (N, 3) to pixels (N, 2) of the raw image shown at `size`.

    The inverse of the region path: into `camera` (the channel's rectified
    camera), rotated back by Rᵀ into the raw camera, distorted with K and D
    (OpenCV's forward model), then scaled from the rig's size to `size`.
    A point at or behind the camera has no pixel (NaN).
    """
    placed = np.asarray(points, np.float64).reshape(-1, 3)
    position = camera.position
    offset = placed - (position.x, position.y, position.z)
    in_camera = offset @ _rotation(camera)  # Rᵀ applied to each row
    rotation = np.array(rig.channels[channel].rotation, np.float64).reshape(3, 3)
    raw_rays = in_camera @ rotation  # rectified -> raw camera: Rᵀ, row-wise
    k = np.array(rig.channels[channel].camera_matrix, np.float64).reshape(3, 3)
    coefficients = np.zeros(8, np.float64)
    distortion = rig.channels[channel].distortion
    coefficients[: len(distortion)] = distortion
    k1, k2, p1, p2, k3, k4, k5, k6 = coefficients.tolist()
    pixels = np.full((len(placed), 2), np.nan)
    ahead = raw_rays[:, 2] > 1e-9
    x = raw_rays[ahead, 0] / raw_rays[ahead, 2]
    y = raw_rays[ahead, 1] / raw_rays[ahead, 2]
    r2 = x * x + y * y
    radial = (1 + ((k3 * r2 + k2) * r2 + k1) * r2) / (1 + ((k6 * r2 + k5) * r2 + k4) * r2)
    xd = x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
    yd = y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
    pixels[ahead, 0] = (k[0, 0] * xd + k[0, 1] * yd + k[0, 2]) * size[0] / rig.width
    pixels[ahead, 1] = (k[1, 1] * yd + k[1, 2]) * size[1] / rig.height
    return pixels


def display_depth(rig: RegionRig, frame: DenseFrame, size: tuple[int, int]) -> NDArray[np.float32]:
    """Depth (m) of each pixel of `frame`'s raw image shown at `size`; 0 where none.

    The region path applied to every pixel: shown pixel centre to raw pixel
    to rectified pixel (rounded as `lround` does), the journalled disparity
    read there and turned into `z = fx * b / d` up to the depth cap. A
    pixel therefore has the depth its region points would have.
    """
    width, height = size
    channel = rig.channels[frame.channel]
    cols, rows = np.meshgrid(
        np.arange(width, dtype=np.float64), np.arange(height, dtype=np.float64)
    )
    # Pixel centres scale onto pixel centres; at the rig's own size this is the identity.
    raw = np.stack(
        [
            (cols.ravel() + 0.5) * rig.width / width - 0.5,
            (rows.ravel() + 0.5) * rig.height / height - 0.5,
        ],
        axis=1,
    )
    rectified = round_half_away(undistort_points(raw, channel))
    u, v = rectified[:, 0], rectified[:, 1]
    inside = (u >= 0) & (u < rig.width) & (v >= 0) & (v < rig.height)
    disparity = decode_disparity(frame.disparity_png)
    subpixels = np.zeros(len(raw), np.float64)
    subpixels[inside] = disparity[v[inside], u[inside]]
    fx = np.array(channel.projection, np.float64)[0]
    with np.errstate(divide="ignore"):
        depth = np.where(
            subpixels > 0, fx * rig.baseline_m / (subpixels / DISPARITY_SUBPIXELS), 0.0
        )
    depth = np.where(depth <= rig.max_depth_m, depth, 0.0)
    shown: NDArray[np.float32] = depth.reshape(height, width).astype(np.float32)
    return shown


class DenseBufferRegionSource:
    """`RegionPointSource` over journalled dense frames; a frame it lacks has expired."""

    def __init__(self, rig: RegionRig, frames: Iterable[DenseFrame]) -> None:
        self._rig = rig
        self._frames = {(frame.frame_id, frame.channel): frame for frame in frames}
        # The newest frame's decoded disparity: SAM's masks on one frame
        # are asked one after another, so one PNG decode serves them all.
        self._decoded: tuple[tuple[int, int], NDArray[np.uint16]] | None = None

    @property
    def region_rig(self) -> RegionRig:
        return self._rig

    def region_points(self, query: RegionQuery, timeout: float = 5.0) -> RegionResult:
        key = (query.frame_id, query.channel)
        frame = self._frames.get(key)
        if frame is None:
            return dense_region_points(query, self._rig, None)
        if self._decoded is None or self._decoded[0] != key:
            self._decoded = (key, decode_disparity(frame.disparity_png))
        return dense_region_points(query, self._rig, frame, self._decoded[1])


@runtime_checkable
class DenseJournalSource(Protocol):
    """A live backend that journals its dense buffer (the streaming sidecar, v5)."""

    @property
    def region_rig(self) -> RegionRig | None: ...
    def poll_dense(self) -> list[DenseFrame]: ...
