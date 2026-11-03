"""Simulated checkerboard: render a known board through a known rig.

Ground truth for calibration tests — the rig intrinsics and baseline
are chosen, the board pose is chosen, so a solver fed rendered pairs
must recover numbers near the chosen ones. The lens is pinhole by
default (SurMap's ELP profile), or distorted with OpenCV's
radial-tangential / rational or equidistant fisheye model so each of
the calibration's lens models has a known truth to recover. Rendering
is Pillow polygon fills of projected squares, no vision dependency;
under distortion each square edge is split so it bends as the lens
bends it. Squares are drawn at
`SUPERSAMPLE`x and box-filtered down: hard-edged fills give a corner
refiner no gradient to work with and bias every corner by up to a
pixel, which a calibration then reads as focal-length and baseline
error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.port import CornerSet, LensModel

SUPERSAMPLE = 8
EDGE_STEPS_DISTORTED = 12


@dataclass(frozen=True)
class BoardPose:
    """Board centre in the left camera frame (x right, y down, z fwd)."""

    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 1.0
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0


@dataclass(frozen=True)
class RenderedPair:
    width: int
    height: int
    left_rgb: bytes
    right_rgb: bytes
    left_corners: CornerSet
    right_corners: CornerSet
    left_board_fraction: float


def _rotation(pose: BoardPose) -> NDArray[np.float64]:
    yaw, pitch, roll = (math.radians(a) for a in (pose.yaw_deg, pose.pitch_deg, pose.roll_deg))
    ry = np.array(
        [[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]]
    )
    rx = np.array(
        [[1, 0, 0], [0, math.cos(pitch), -math.sin(pitch)], [0, math.sin(pitch), math.cos(pitch)]]
    )
    rz = np.array(
        [[math.cos(roll), -math.sin(roll), 0], [math.sin(roll), math.cos(roll), 0], [0, 0, 1]]
    )
    return np.asarray(rz @ rx @ ry, dtype=np.float64)


@dataclass(frozen=True)
class StereoRig:
    """A stereo pair of identical cameras, `baseline_m` apart along x."""

    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    baseline_m: float
    lens: LensModel = LensModel.PINHOLE_RADTAN
    distortion: tuple[float, ...] = ()
    """In `lens`'s OpenCV order; empty for an ideal pinhole."""


class SimulatedCheckerboard:
    """A checkerboard rendered through one declared stereo rig."""

    def __init__(self, *, board: CheckerboardSpec, rig: StereoRig) -> None:
        self._board = board
        self._width, self._height = rig.width, rig.height
        self._fx, self._fy, self._cx, self._cy = rig.fx, rig.fy, rig.cx, rig.cy
        self._baseline = rig.baseline_m
        self._lens = rig.lens
        self._distortion = rig.distortion

    def _distort(self, x: float, y: float) -> tuple[float, float]:
        """Normalized image point through the lens (OpenCV's models)."""
        d = self._distortion
        if not d and self._lens is not LensModel.FISHEYE:
            return x, y
        if self._lens is LensModel.FISHEYE:
            k1, k2, k3, k4 = (*d, 0.0, 0.0, 0.0, 0.0)[:4]
            r = math.hypot(x, y)
            if r < 1e-12:
                return x, y
            theta = math.atan(r)
            t2 = theta * theta
            theta_d = theta * (1 + k1 * t2 + k2 * t2**2 + k3 * t2**3 + k4 * t2**4)
            return x * theta_d / r, y * theta_d / r
        k1, k2, p1, p2, k3, k4, k5, k6 = (*d, *(0.0,) * 8)[:8]
        r2 = x * x + y * y
        radial = (1 + k1 * r2 + k2 * r2**2 + k3 * r2**3) / (1 + k4 * r2 + k5 * r2**2 + k6 * r2**3)
        return (
            x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x),
            y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y,
        )

    def _project(self, points: NDArray[np.float64], eye_x_m: float) -> CornerSet:
        out = []
        for x, y, z in points:
            zz = float(z)
            xd, yd = self._distort((float(x) - eye_x_m) / zz, float(y) / zz)
            out.append((self._fx * xd + self._cx, self._fy * yd + self._cy))
        return tuple(out)

    def _outline(
        self, corners: tuple[tuple[float, float, float], ...]
    ) -> tuple[tuple[float, float, float], ...]:
        """A board-plane polygon, its edges split when the lens bends them."""
        straight = not self._distortion and self._lens is not LensModel.FISHEYE
        steps = 1 if straight else EDGE_STEPS_DISTORTED
        out = []
        for (ax, ay, az), (bx, by, bz) in zip(corners, corners[1:] + corners[:1], strict=True):
            for i in range(steps):
                t = i / steps
                out.append((ax + (bx - ax) * t, ay + (by - ay) * t, az + (bz - az) * t))
        return tuple(out)

    def _board_points_cam(
        self, pose: BoardPose, grid: tuple[tuple[float, float, float], ...]
    ) -> NDArray[np.float64]:
        rot = _rotation(pose)
        centre = np.array(
            [
                (self._board.cols - 1) * self._board.square_size_m / 2,
                (self._board.rows - 1) * self._board.square_size_m / 2,
                0.0,
            ]
        )
        local = np.array(grid, dtype=np.float64) - centre
        return np.asarray(
            local @ rot.T + np.array([pose.x_m, pose.y_m, pose.z_m]), dtype=np.float64
        )

    def project_corners(self, pose: BoardPose) -> tuple[CornerSet, CornerSet]:
        cam = self._board_points_cam(pose, self._board.object_points())
        return self._project(cam, 0.0), self._project(cam, self._baseline)

    def render_pair(self, pose: BoardPose) -> RenderedPair:
        left = self._render(pose, 0.0)
        right = self._render(pose, self._baseline)
        lc, rc = self.project_corners(pose)
        us = [p[0] for p in self._square_corners_px(pose, 0.0)]
        vs = [p[1] for p in self._square_corners_px(pose, 0.0)]
        fraction = ((max(us) - min(us)) * (max(vs) - min(vs))) / (self._width * self._height)
        return RenderedPair(self._width, self._height, left, right, lc, rc, fraction)

    def _square_corners_px(self, pose: BoardPose, eye_x_m: float) -> list[tuple[float, float]]:
        s = self._board.square_size_m
        grid = tuple(
            (c * s, r * s, 0.0)
            for r in range(self._board.rows + 2)
            for c in range(self._board.cols + 2)
        )
        # Shift so grid spans the full board (inner corners offset by one square).
        shifted = tuple((x - s, y - s, z) for x, y, z in grid)
        cam = self._board_points_cam(pose, shifted)
        return list(self._project(cam, eye_x_m))

    def _render(self, pose: BoardPose, eye_x_m: float) -> bytes:
        k = SUPERSAMPLE
        image = Image.new("L", (self._width * k, self._height * k), 160)
        draw = ImageDraw.Draw(image)

        def hi_res(points: CornerSet) -> list[tuple[float, float]]:
            # Pixel centres sit on integers at both scales, so a pixel
            # coordinate p lands at (p + 0.5)·k − 0.5 when supersampled.
            return [((u + 0.5) * k - 0.5, (v + 0.5) * k - 0.5) for u, v in points]

        s = self._board.square_size_m
        # White quiet-zone backing, one square larger than the board.
        backing = tuple(
            (x, y, 0.0)
            for x, y in (
                (-s, -s),
                (self._board.board_width_m - s, -s),
                (self._board.board_width_m - s, self._board.board_height_m - s),
                (-s, self._board.board_height_m - s),
            )
        )
        cam = self._board_points_cam(pose, self._outline(backing))
        draw.polygon(hi_res(self._project(cam, eye_x_m)), fill=255)
        for r in range(self._board.rows + 1):
            for c in range(self._board.cols + 1):
                corners = tuple(
                    ((c - 1) * s + dx, (r - 1) * s + dy, 0.0)
                    for dx, dy in ((0.0, 0.0), (s, 0.0), (s, s), (0.0, s))
                )
                cam_sq = self._board_points_cam(pose, self._outline(corners))
                draw.polygon(
                    hi_res(self._project(cam_sq, eye_x_m)), fill=0 if (r + c) % 2 == 0 else 255
                )
        frame = image.resize((self._width, self._height), Image.Resampling.BOX)
        return bytes(frame.convert("RGB").tobytes())
