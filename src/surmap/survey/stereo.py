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

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

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
    raise NotImplementedError("TODO(cm5-stereo): implement decode_grayscale")


class StereoReconstructor:
    """Reconstructs camera-frame scene points from one stereo pair."""

    def __init__(
        self,
        max_disparity: int = 48,
        min_depth_m: float = 0.2,
        max_depth_m: float = 8.0,
        stride: int = 2,
        max_points: int = 20_000,
    ) -> None:
        self._max_disparity = max_disparity
        self._min_depth_m = min_depth_m
        self._max_depth_m = max_depth_m
        self._stride = stride
        self._max_points = max_points

    def reconstruct(
        self, left: FrameImage, right: FrameImage, rig: StereoRig
    ) -> tuple[Vec3, ...]:
        """Camera-frame points seen by both cameras in this pair."""
        raise NotImplementedError("TODO(cm5-stereo): implement reconstruct")
