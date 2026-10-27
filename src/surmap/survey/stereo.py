"""Real stereo reconstruction for the CM5: frames in, scene points out.

Decodes a streamed stereo pair, aligns the right image to the left
(the rig's pairs are not rectified, so the alignment is estimated per
pair), block-matches disparities, and back-projects them to
camera-frame points with the rig's calibration. Pure numpy/Pillow —
no native dependency, so this runs identically on the CM5, in CI, and
in simulation. Pose (and therefore the map frame) stays with the
`SlamBackend` port; this module produces camera-frame points only.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.types import Vec3


@dataclass(frozen=True)
class StereoRig:
    """One stereo rig's calibration, at the frames' own resolution."""

    fx: float
    fy: float
    cx: float
    cy: float
    baseline_m: float


@dataclass(frozen=True)
class FrameImage:
    """One raw frame as the reconstructor consumes it."""

    width: int
    height: int
    encoding: str  # "mjpeg" | "raw_rgb"
    data: bytes


def decode_grayscale(frame: FrameImage) -> NDArray[np.float32]:
    """Decode one frame to a float32 grayscale image (H x W)."""
    if frame.encoding == "raw_rgb":
        expected = frame.width * frame.height * 3
        if len(frame.data) != expected:
            raise ValueError(f"raw_rgb frame has {len(frame.data)} bytes, expected {expected}")
        rgb = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 3)
        return np.asarray(rgb.mean(axis=2), dtype=np.float32)
    if frame.encoding == "mjpeg":
        try:
            with Image.open(io.BytesIO(frame.data)) as image:
                gray: NDArray[np.float32] = np.asarray(image.convert("L"), dtype=np.float32)
                return gray
        except Exception as exc:
            raise ValueError(f"undecodable mjpeg frame: {exc}") from exc
    raise ValueError(f"unsupported frame encoding: {frame.encoding}")


def _shift_image(image: NDArray[np.float32], dx: int, dy: int) -> NDArray[np.float32]:
    """`image` with its content moved by (dx, dy); vacated pixels are 0."""
    out = np.zeros_like(image)
    h, w = image.shape
    src_x = slice(max(0, -dx), min(w, w - dx))
    dst_x = slice(max(0, dx), min(w, w + dx))
    src_y = slice(max(0, -dy), min(h, h - dy))
    dst_y = slice(max(0, dy), min(h, h + dy))
    out[dst_y, dst_x] = image[src_y, src_x]
    return np.asarray(out, dtype=np.float32)


def _box_sum(image: NDArray[np.float32], half: int) -> NDArray[np.float32]:
    """Sum over a (2*half+1)^2 window at every pixel (edge-padded)."""
    padded = np.pad(image, half, mode="edge")
    integral = np.pad(padded, ((1, 0), (1, 0)), mode="constant").cumsum(0).cumsum(1)
    size = 2 * half + 1
    return (
        integral[size:, size:]
        - integral[:-size, size:]
        - integral[size:, :-size]
        + integral[:-size, :-size]
    )


def _disparity_map(
    left: NDArray[np.float32], right: NDArray[np.float32], max_disparity: int
) -> NDArray[np.float32]:
    """Best-match disparity of `right` against `left`, per pixel.

    A match at disparity d pairs left pixel x with right pixel x + d
    (this rig's geometry, after principal-point alignment). Pixels
    whose best window cost is not convincing keep disparity 0.
    """
    half = 3
    height, width = left.shape
    best = np.full((height, width), np.inf, dtype=np.float32)
    disparity = np.zeros((height, width), dtype=np.float32)
    padded_left = np.pad(left, half, mode="edge")
    for d in range(2, max_disparity + 1):
        shifted = _shift_image(right, -d, 0)
        padded_right = np.pad(shifted, half, mode="edge")
        cost = _box_sum(np.abs(padded_left - padded_right), half) / float((2 * half + 1) ** 2)
        cost = cost[half : half + height, half : half + width]
        better = cost < best
        best = np.where(better, cost, best)
        disparity = np.where(better, float(d), disparity)
    disparity = np.where(best < 20.0, disparity, 0.0)
    return disparity


class StereoReconstructor:
    """Reconstructs camera-frame scene points from one stereo pair."""

    def __init__(
        self,
        max_disparity: int = 64,
        min_depth_m: float = 0.2,
        max_depth_m: float = 8.0,
        stride: int = 2,
        max_points: int = 20_000,
        alignment_offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self._max_disparity = max_disparity
        self._min_depth_m = min_depth_m
        self._max_depth_m = max_depth_m
        self._stride = stride
        self._max_points = max_points
        # Right principal point minus left, in frame pixels: the shift
        # that rectifies this rig's pairs before matching.
        self._alignment_offset = alignment_offset

    def reconstruct(self, left: FrameImage, right: FrameImage, rig: StereoRig) -> tuple[Vec3, ...]:
        """Camera-frame points seen by both cameras in this pair."""
        left_gray = decode_grayscale(left)
        right_gray = decode_grayscale(right)
        # The rig's two cameras need not deliver identically sized frames.
        common_h = min(left_gray.shape[0], right_gray.shape[0])
        common_w = min(left_gray.shape[1], right_gray.shape[1])
        left_gray = left_gray[:common_h, :common_w]
        right_gray = right_gray[:common_h, :common_w]
        scale = max(1, left_gray.shape[1] // 160)
        small_left = left_gray[::scale, ::scale]
        small_right = right_gray[::scale, ::scale]
        offset_x, offset_y = self._alignment_offset
        aligned_right = _shift_image(small_right, round(offset_x / scale), round(offset_y / scale))

        disparity = _disparity_map(small_left, aligned_right, self._max_disparity)
        # Reverse disparity (right -> left), computed in flipped coordinates
        # so the same matching convention applies, then unflipped.
        reverse = _disparity_map(aligned_right[:, ::-1], small_left[:, ::-1], self._max_disparity)[
            :, ::-1
        ]
        height, width = disparity.shape
        cols = np.arange(width, dtype=np.int32)[None, :]
        partner = np.clip(cols + disparity.astype(np.int32), 0, width - 1)
        reverse_at_partner = np.take_along_axis(reverse, partner, axis=1)
        consistent = np.abs(reverse_at_partner - disparity) <= 1.0

        fx = rig.fx / scale
        fy = rig.fy / scale
        cx = rig.cx / scale
        cy = rig.cy / scale
        with np.errstate(divide="ignore", invalid="ignore"):
            depth = np.where(disparity >= 2, fx * rig.baseline_m / np.maximum(disparity, 1.0), 0.0)
        valid = consistent & (depth >= self._min_depth_m) & (depth <= self._max_depth_m)
        rows, cols_out = np.nonzero(valid[:: self._stride, :: self._stride])
        rows = rows * self._stride
        cols_out = cols_out * self._stride
        if len(rows) > self._max_points:
            pick = np.linspace(0, len(rows) - 1, self._max_points).astype(int)
            rows, cols_out = rows[pick], cols_out[pick]
        points = []
        for row, col in zip(rows.tolist(), cols_out.tolist(), strict=True):
            z = float(depth[row, col])
            points.append(Vec3((col - cx) * z / fx, (row - cy) * z / fy, z))
        return tuple(points)
