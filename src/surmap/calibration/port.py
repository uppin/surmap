"""Port for checkerboard vision (hexagon seam).

The domain (session, guidance, RPC session logic) speaks only these
contracts. The adapter is `OpenCvSidecarVision` (real OpenCV in a sidecar
process); tests script their own. No
OpenCV or protobuf type crosses this seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from surmap.calibration.board import CheckerboardSpec

CornerSet = tuple[tuple[float, float], ...]
"""Pixel corners (u, v), row-major over the board's inner grid."""


@dataclass(frozen=True)
class EncodedFrame:
    """One camera frame as it arrives: size, encoding and bytes."""

    frame_id: int
    width: int
    height: int
    encoding: str
    """"raw_rgb" or "mjpeg"."""
    data: bytes


@dataclass(frozen=True)
class CalibrationView:
    """One accepted stereo view: corners in both eyes."""

    left: CornerSet
    right: CornerSet


class LensModel(Enum):
    """The camera models RTAB-Map's calibration dialog solves."""

    PINHOLE_RADTAN = "pinhole_radtan"
    """Plumb bob, k1, k2, p1, p2 (k3 held at 0) — SurMap's default."""
    PINHOLE_RATIONAL = "pinhole_rational"
    """OpenCV rational: k1, k2, p1, p2, k3, k4, k5, k6."""
    FISHEYE = "fisheye"
    """Equidistant (cv::fisheye): k1, k2, k3, k4."""


@dataclass(frozen=True)
class StereoEstimate:
    """Solved stereo calibration; distortion in the order `lens` defines."""

    left_fx: float
    left_fy: float
    left_cx: float
    left_cy: float
    right_fx: float
    right_fy: float
    right_cx: float
    right_cy: float
    distortion_left: tuple[float, ...]
    distortion_right: tuple[float, ...]
    rotation: tuple[float, ...]
    """Left camera to right camera, row-major 3x3 (x_r = R·x_l + T)."""
    translation_m: tuple[float, float, float]
    baseline_m: float
    rms_left: float
    rms_right: float
    rms_stereo: float
    views_used: int
    lens: LensModel
    baseline_scale: float = 1.0
    """Applied to the solved translation (1.0 unless rescaled to a known baseline)."""

    @property
    def solved_baseline_m(self) -> float:
        """The baseline the solve itself produced, before any rescale."""
        return self.baseline_m / self.baseline_scale


class CheckerboardVision(Protocol):
    """What calibration needs from a vision engine."""

    async def detect(
        self, frame: EncodedFrame, *, board: CheckerboardSpec, max_scale: int
    ) -> CornerSet | None:
        """Board corners in one frame, or None when not found.

        Detection retries on the frame upscaled 2x .. `max_scale`x (as
        RTAB-Map does for small boards); corners are in native pixels.

        Raises `UnreadableFrame` when the bytes cannot be decoded.
        """
        ...

    async def calibrate(
        self,
        *,
        views: tuple[CalibrationView, ...],
        board: CheckerboardSpec,
        width: int,
        height: int,
        lens: LensModel,
    ) -> StereoEstimate:
        """Solve both eyes plus the stereo extrinsic from `views`."""
        ...


class CalibrationUnavailable(RuntimeError):
    """Raised when no usable vision adapter can be constructed."""


class UnreadableFrame(ValueError):
    """One frame's bytes could not be decoded; the stream may go on."""
