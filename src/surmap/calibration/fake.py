"""Scripted `CheckerboardVision` for tests and simulation runs."""

from __future__ import annotations

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.port import CalibrationView, CornerSet, LensModel, StereoEstimate


class ScriptedCheckerboardVision:
    """Returns corners scripted by frame_id; solves to a fixed estimate."""

    def __init__(
        self,
        corners_by_frame: dict[int, CornerSet | None],
        estimate: StereoEstimate | None = None,
    ) -> None:
        self._corners = corners_by_frame
        self._estimate = estimate

    async def detect(
        self,
        *,
        frame_id: int,
        width: int,
        height: int,
        encoding: str,
        data: bytes,
        board: CheckerboardSpec,
        max_scale: int,
    ) -> CornerSet | None:
        return self._corners.get(frame_id)

    async def calibrate(
        self,
        *,
        views: tuple[CalibrationView, ...],
        board: CheckerboardSpec,
        width: int,
        height: int,
        lens: LensModel,
    ) -> StereoEstimate:
        if self._estimate is not None:
            return self._estimate
        return StereoEstimate(
            left_fx=380.0,
            left_fy=380.0,
            left_cx=width / 2,
            left_cy=height / 2,
            right_fx=380.0,
            right_fy=380.0,
            right_cx=width / 2,
            right_cy=height / 2,
            distortion_left=(0.0,) * 4,
            distortion_right=(0.0,) * 4,
            rotation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            translation_m=(-0.07, 0.0, 0.0),
            baseline_m=0.07,
            rms_left=0.1,
            rms_right=0.1,
            rms_stereo=0.1,
            views_used=len(views),
            lens=lens,
        )
