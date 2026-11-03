"""CameraCalibrationService.StreamCalibration (BIDI).

Config (explicit checkerboard target) first, then stereo pairs, then
finish. As soon as the image size is known the first response is the
capture plan — every viewpoint the calibration needs. Per pair: detect
in both eyes via the `CheckerboardVision` port, feed the session, and
stream its feedback (status, spreads, the viewpoint it filled, the
next-pose suggestion). A pair that cannot be decoded is reported and
the stream goes on; a finish before the views are diverse enough is
answered `not_ready` and the stream goes on. On a ready finish: solve
via the port with the configured lens model, rescale to the expected
baseline when one is given, and stream the estimated stereo calibration
(`surmap.calibration.export` turns it into EuRoC `sensor.yaml`s).

Contract violations end the stream: no config first, a target other
than checkerboard, or a frame whose size differs from the stream's
(the config's, or the first frame's when the config leaves it 0).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Any

from surmap.calibration.baseline import rescale_baseline
from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.plan import Tilt, Viewpoint
from surmap.calibration.port import (
    CheckerboardVision,
    CornerSet,
    EncodedFrame,
    LensModel,
    StereoEstimate,
    UnreadableFrame,
)
from surmap.calibration.session import CalibrationSession, ViewFeedback, ViewStatus
from surmap.rpc.compose import Brick
from surmap.rpc.description import ServiceModule
from surmap.survey.v1 import survey_pb2

_STATUS = {
    ViewStatus.ACCEPTED: survey_pb2.CALIBRATION_VIEW_ACCEPTED,
    ViewStatus.BOARD_NOT_FOUND: survey_pb2.CALIBRATION_VIEW_BOARD_NOT_FOUND,
    ViewStatus.TOO_SIMILAR: survey_pb2.CALIBRATION_VIEW_TOO_SIMILAR,
    ViewStatus.FRAME_UNREADABLE: survey_pb2.CALIBRATION_VIEW_FRAME_UNREADABLE,
    ViewStatus.NO_VIEW: survey_pb2.CALIBRATION_VIEW_UNSPECIFIED,
}

_LENS = {
    survey_pb2.CALIBRATION_LENS_UNSPECIFIED: LensModel.PINHOLE_RADTAN,
    survey_pb2.CALIBRATION_LENS_PINHOLE_RADTAN: LensModel.PINHOLE_RADTAN,
    survey_pb2.CALIBRATION_LENS_PINHOLE_RATIONAL: LensModel.PINHOLE_RATIONAL,
    survey_pb2.CALIBRATION_LENS_FISHEYE: LensModel.FISHEYE,
}
_LENS_PROTO = {
    LensModel.PINHOLE_RADTAN: survey_pb2.CALIBRATION_LENS_PINHOLE_RADTAN,
    LensModel.PINHOLE_RATIONAL: survey_pb2.CALIBRATION_LENS_PINHOLE_RATIONAL,
    LensModel.FISHEYE: survey_pb2.CALIBRATION_LENS_FISHEYE,
}
_TILT = {
    Tilt.NONE: survey_pb2.CALIBRATION_TILT_NONE,
    Tilt.TOP_LEFT_AWAY: survey_pb2.CALIBRATION_TILT_TOP_LEFT_AWAY,
    Tilt.TOP_RIGHT_AWAY: survey_pb2.CALIBRATION_TILT_TOP_RIGHT_AWAY,
    Tilt.BOTTOM_LEFT_AWAY: survey_pb2.CALIBRATION_TILT_BOTTOM_LEFT_AWAY,
    Tilt.BOTTOM_RIGHT_AWAY: survey_pb2.CALIBRATION_TILT_BOTTOM_RIGHT_AWAY,
}
MAX_DETECTION_SCALE = 3
"""RTAB-Map's limit for upscaled detection."""

_ENCODING = {
    survey_pb2.FRAME_ENCODING_MJPEG: "mjpeg",
    survey_pb2.FRAME_ENCODING_RAW_RGB: "raw_rgb",
}


def _feedback_message(feedback: ViewFeedback) -> survey_pb2.CalibrationFeedback:
    s = feedback.suggestion
    return survey_pb2.CalibrationFeedback(
        frame_id=feedback.frame_id,
        status=_STATUS[feedback.status],
        left_found=feedback.left_found,
        right_found=feedback.right_found,
        corners_left=feedback.corners_left,
        corners_right=feedback.corners_right,
        board_center_x=feedback.board_center_x,
        board_center_y=feedback.board_center_y,
        board_fraction=feedback.board_fraction,
        board_size=feedback.board_size,
        board_skew=feedback.board_skew,
        accepted_views=feedback.accepted_views,
        required_views=feedback.required_views,
        coverage_fraction=feedback.coverage_fraction,
        x_spread=feedback.x_spread,
        y_spread=feedback.y_spread,
        size_spread=feedback.size_spread,
        skew_spread=feedback.skew_spread,
        ready=feedback.ready,
        suggestion=survey_pb2.MoveSuggestion(
            target_cell=s.target_cell,
            move_x_m=s.move_x_m,
            move_y_m=s.move_y_m,
            move_z_m=s.move_z_m,
            target_distance_m=s.target_distance_m,
            instruction=s.instruction,
            viewpoint_index=s.viewpoint_index,
        ),
        message=feedback.message,
        matched_viewpoint=feedback.matched_viewpoint,
        remaining_viewpoints=feedback.remaining_viewpoints,
    )


def _plan_proto(plan: tuple[Viewpoint, ...]) -> survey_pb2.CalibrationResponse:
    return survey_pb2.CalibrationResponse(
        plan=survey_pb2.CalibrationPlan(
            viewpoints=[
                survey_pb2.CalibrationViewpoint(
                    index=v.index,
                    target_cell=v.target_cell,
                    center_x=v.center_x,
                    center_y=v.center_y,
                    board_size=v.board_size,
                    tilt=_TILT[v.tilt],
                    tilt_deg=v.tilt_deg,
                    distance_m=v.distance_m,
                    instruction=v.instruction,
                )
                for v in plan
            ]
        )
    )


def _result_proto(
    estimate: StereoEstimate, board: CheckerboardSpec, width: int, height: int
) -> survey_pb2.CalibrationResponse:
    return survey_pb2.CalibrationResponse(
        result=survey_pb2.EstimatedStereoCalibration(
            calibration=survey_pb2.StereoCalibration(
                calibration_id=f"checkerboard-{board.cols}x{board.rows}",
                focal_length_px=(estimate.left_fx + estimate.right_fx) / 2,
                baseline_m=estimate.baseline_m,
                cx=estimate.left_cx,
                cy=estimate.left_cy,
                width=width,
                height=height,
            ),
            left_fx=estimate.left_fx,
            left_fy=estimate.left_fy,
            right_fx=estimate.right_fx,
            right_fy=estimate.right_fy,
            baseline_m=estimate.baseline_m,
            rms_left=estimate.rms_left,
            rms_right=estimate.rms_right,
            rms_stereo=estimate.rms_stereo,
            views_used=estimate.views_used,
            distortion_left=estimate.distortion_left,
            distortion_right=estimate.distortion_right,
            rotation=estimate.rotation,
            translation_m=estimate.translation_m,
            lens_model=_LENS_PROTO[estimate.lens],
            baseline_scale=estimate.baseline_scale,
            implied_square_size_m=board.square_size_m * estimate.baseline_scale,
            solved_baseline_m=estimate.solved_baseline_m,
        )
    )


def _frame_size(pair: survey_pb2.CalibrationStereoFrame) -> tuple[int, int]:
    left = (int(pair.left.width), int(pair.left.height))
    right = (int(pair.right.width), int(pair.right.height))
    if left != right:
        raise ValueError(
            f"calibration pair eyes differ in size: left {left[0]}x{left[1]}, "
            f"right {right[0]}x{right[1]}"
        )
    return left


@dataclass(frozen=True)
class _StreamOptions:
    max_detection_scale: int
    expected_baseline_m: float


def _session_from_config(
    config: survey_pb2.CalibrationConfig,
) -> tuple[CalibrationSession, _StreamOptions]:
    if config.target_type != survey_pb2.CALIBRATION_TARGET_CHECKERBOARD:
        raise ValueError(
            "calibration target must be explicitly checkerboard (CALIBRATION_TARGET_CHECKERBOARD)"
        )
    if not config.HasField("checkerboard"):
        raise ValueError("checkerboard config missing its CheckerboardSpec")
    max_scale = int(config.max_detection_scale) or 1
    if max_scale > MAX_DETECTION_SCALE:
        raise ValueError(f"max_detection_scale must be 1..{MAX_DETECTION_SCALE}, got {max_scale}")
    if config.expected_baseline_m < 0:
        raise ValueError("expected_baseline_m must be positive, or 0 to keep the solved one")
    proto_board = config.checkerboard
    session = CalibrationSession(
        board=CheckerboardSpec(
            cols=int(proto_board.cols),
            rows=int(proto_board.rows),
            square_size_m=float(proto_board.square_size_m),
        ),
        width=int(config.width),
        height=int(config.height),
        min_views=int(config.min_views) or 8,
        lens=_LENS[config.lens_model],
    )
    return session, _StreamOptions(max_scale, float(config.expected_baseline_m))


async def _detect_pair(
    vision: CheckerboardVision,
    pair: survey_pb2.CalibrationStereoFrame,
    board: CheckerboardSpec,
    max_scale: int,
) -> tuple[CornerSet | None, CornerSet | None]:
    async def detect(frame: survey_pb2.RawVideoFrame) -> CornerSet | None:
        encoded = EncodedFrame(
            frame_id=int(frame.frame_id),
            width=int(frame.width),
            height=int(frame.height),
            encoding=_ENCODING.get(frame.encoding, "raw_rgb"),
            data=frame.data,
        )
        return await vision.detect(encoded, board=board, max_scale=max_scale)

    left, right = await asyncio.gather(detect(pair.left), detect(pair.right))
    return left, right


def _bind_size(session: CalibrationSession, pair: survey_pb2.CalibrationStereoFrame) -> None:
    """Take the stream's size from its first frame (config left it 0)."""
    session.width, session.height = _frame_size(pair)


async def _observe_pair(
    session: CalibrationSession,
    vision: CheckerboardVision,
    pair: survey_pb2.CalibrationStereoFrame,
    max_scale: int,
) -> ViewFeedback:
    size = _frame_size(pair)
    if size != (session.width, session.height):
        raise ValueError(
            f"calibration frame is {size[0]}x{size[1]}, but this stream calibrates "
            f"{session.width}x{session.height}"
        )
    frame_id = int(pair.left.frame_id)
    try:
        left, right = await _detect_pair(vision, pair, session.board, max_scale)
    except UnreadableFrame as exc:
        return session.unreadable(frame_id=frame_id, reason=str(exc))
    return session.observe(frame_id=frame_id, left=left, right=right)


async def _frame_responses(
    session: CalibrationSession,
    vision: CheckerboardVision,
    frame: survey_pb2.CalibrationStereoFrame,
    options: _StreamOptions,
) -> list[survey_pb2.CalibrationResponse]:
    """A pair's feedback, preceded by the plan when this frame fixed the size."""
    responses = []
    if not session.plan:
        _bind_size(session, frame)
        responses.append(_plan_proto(session.plan))
    feedback = await _observe_pair(session, vision, frame, options.max_detection_scale)
    responses.append(survey_pb2.CalibrationResponse(feedback=_feedback_message(feedback)))
    return responses


async def _finish_response(
    session: CalibrationSession, vision: CheckerboardVision, options: _StreamOptions
) -> survey_pb2.CalibrationResponse:
    """The solved calibration, or `not_ready` with the progress so far."""
    if not session.ready:
        progress = session.progress(
            f"Not ready to solve: {len(session.views)} of {session.min_views} views, "
            "and the views must spread across position, distance and tilt."
        )
        return survey_pb2.CalibrationResponse(not_ready=_feedback_message(progress))
    estimate = await vision.calibrate(
        views=session.views,
        board=session.board,
        width=session.width,
        height=session.height,
        lens=session.lens,
    )
    if options.expected_baseline_m > 0:
        estimate = rescale_baseline(estimate, expected_baseline_m=options.expected_baseline_m)
    return _result_proto(estimate, session.board, session.width, session.height)


async def stream_calibration(
    requests: AsyncIterable[survey_pb2.CalibrationRequest],
    vision: CheckerboardVision,
) -> AsyncIterator[survey_pb2.CalibrationResponse]:
    """Serve one calibration stream: config, stereo frames, finish."""
    session: CalibrationSession | None = None
    options = _StreamOptions(max_detection_scale=1, expected_baseline_m=0.0)
    async for request in requests:
        kind = request.WhichOneof("kind")
        responses: list[survey_pb2.CalibrationResponse] = []
        if session is None:
            if kind != "config":
                raise ValueError("first calibration request must be config")
            session, options = _session_from_config(request.config)
            responses = [_plan_proto(session.plan)] if session.plan else []
        elif kind == "frame":
            responses = await _frame_responses(session, vision, request.frame, options)
        elif kind == "finish" and request.finish:
            responses = [await _finish_response(session, vision, options)]
        for response in responses:
            yield response
    if session is None:
        raise ValueError("first calibration request must be config")


def calibration_service_module(vision: CheckerboardVision) -> ServiceModule[Any]:
    """The `surmap.rpc` service module mounting `CameraCalibrationService`."""

    def bricks(_ctx: Any) -> tuple[Brick, ...]:
        async def handler(
            requests: AsyncIterable[survey_pb2.CalibrationRequest], _ctx2: Any
        ) -> AsyncIterator[survey_pb2.CalibrationResponse]:
            async for response in stream_calibration(requests, vision):
                yield response

        return (Brick(methods={"StreamCalibration": handler}),)

    return ServiceModule(
        descriptor=survey_pb2.DESCRIPTOR.services_by_name["CameraCalibrationService"],
        bricks=bricks,
    )
