"""CameraCalibrationService.StreamCalibration (BIDI) over fake OpenCV."""

from collections.abc import AsyncIterable

import pytest

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.port import (
    CalibrationView,
    CornerSet,
    EncodedFrame,
    LensModel,
    StereoEstimate,
    UnreadableFrame,
)
from surmap.calibration.service import stream_calibration
from surmap.survey.v1 import survey_pb2
from tests.calibration_builders import DIVERSE_VIEWS


class FakeDetector:
    """Scripted adapter for the calibration port, standing in for OpenCV.

    Frame n (1-based) shows `DIVERSE_VIEWS[n - 1]` in both eyes; frames
    in `unreadable` fail to decode.
    """

    def __init__(self, unreadable: frozenset[int] = frozenset()) -> None:
        self._unreadable = unreadable
        self.max_scales: list[int] = []
        self.lenses: list[LensModel] = []

    async def detect(
        self, frame: EncodedFrame, *, board: CheckerboardSpec, max_scale: int
    ) -> CornerSet | None:
        frame_id = frame.frame_id
        self.max_scales.append(max_scale)
        if frame_id in self._unreadable:
            raise UnreadableFrame(f"frame {frame_id} is not decodable")
        if not 1 <= frame_id <= len(DIVERSE_VIEWS):
            return None
        return DIVERSE_VIEWS[frame_id - 1]

    async def calibrate(
        self,
        *,
        views: tuple[CalibrationView, ...],
        board: CheckerboardSpec,
        width: int,
        height: int,
        lens: LensModel,
    ) -> StereoEstimate:
        self.lenses.append(lens)
        return StereoEstimate(
            left_fx=380.0,
            left_fy=381.0,
            left_cx=320.0,
            left_cy=240.0,
            right_fx=379.0,
            right_fy=380.0,
            right_cx=318.0,
            right_cy=239.0,
            distortion_left=(0.0, 0.0, 0.0, 0.0),
            distortion_right=(0.0, 0.0, 0.0, 0.0),
            rotation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            translation_m=(-0.07, 0.0, 0.0),
            baseline_m=0.07,
            rms_left=0.21,
            rms_right=0.22,
            rms_stereo=0.25,
            views_used=len(views),
            lens=lens,
        )


async def as_stream(
    items: list[survey_pb2.CalibrationRequest],
) -> AsyncIterable[survey_pb2.CalibrationRequest]:
    for item in items:
        yield item


def a_config(
    target: survey_pb2.CalibrationTargetType = survey_pb2.CALIBRATION_TARGET_CHECKERBOARD,
    *,
    width: int = 640,
    height: int = 480,
    lens_model: survey_pb2.CalibrationLensModel = survey_pb2.CALIBRATION_LENS_UNSPECIFIED,
    max_detection_scale: int = 0,
    expected_baseline_m: float = 0.0,
) -> survey_pb2.CalibrationRequest:
    return survey_pb2.CalibrationRequest(
        config=survey_pb2.CalibrationConfig(
            target_type=target,
            checkerboard=survey_pb2.CheckerboardSpec(cols=9, rows=6, square_size_m=0.025),
            min_views=4,
            width=width,
            height=height,
            lens_model=lens_model,
            max_detection_scale=max_detection_scale,
            expected_baseline_m=expected_baseline_m,
        )
    )


def a_pair(frame_id: int, *, width: int = 640, height: int = 480) -> survey_pb2.CalibrationRequest:
    def frame(channel: int) -> survey_pb2.RawVideoFrame:
        return survey_pb2.RawVideoFrame(
            frame_id=frame_id,
            t_ns=frame_id,
            channel=channel,
            width=width,
            height=height,
            encoding=survey_pb2.FRAME_ENCODING_RAW_RGB,
            data=b"\x00" * 12,
        )

    return survey_pb2.CalibrationRequest(
        frame=survey_pb2.CalibrationStereoFrame(left=frame(0), right=frame(1))
    )


FINISH = survey_pb2.CalibrationRequest(finish=True)
FOUR_DIVERSE_PAIRS = [a_pair(1), a_pair(2), a_pair(3), a_pair(4)]


async def collect(
    items: list[survey_pb2.CalibrationRequest], detector: FakeDetector | None = None
) -> list[survey_pb2.CalibrationResponse]:
    vision = detector or FakeDetector()
    return [r async for r in stream_calibration(as_stream(items), vision)]


async def test_checkerboard_frames_stream_feedback_with_a_next_pose_suggestion() -> None:
    # Given a checkerboard config and one good stereo frame
    responses = await collect([a_config(), a_pair(1)])

    # Then one feedback names the pair, counts the view and suggests the next pose
    feedback = responses[1].feedback
    assert feedback.frame_id == 1
    assert feedback.status == survey_pb2.CALIBRATION_VIEW_ACCEPTED
    assert feedback.left_found and feedback.right_found
    assert feedback.accepted_views == 1
    assert feedback.suggestion.target_cell != ""


async def test_feedback_reports_the_spread_of_accepted_views() -> None:
    # Given four views spanning position, size and tilt
    responses = await collect([a_config(), *FOUR_DIVERSE_PAIRS])

    # Then the last feedback carries RTAB-Map's four spreads and is ready
    feedback = responses[-1].feedback
    assert feedback.x_spread > 0.5 and feedback.y_spread > 0.5
    assert feedback.size_spread > 0.4 and feedback.skew_spread > 0.5
    assert feedback.ready


async def test_finish_returns_the_solved_stereo_calibration() -> None:
    # Given four diverse views and a finish marker
    responses = await collect([a_config(), *FOUR_DIVERSE_PAIRS, FINISH])

    # Then the last response is the solved calibration, 7 cm baseline, with its extrinsic
    result = responses[-1].result
    assert result.calibration.calibration_id == "checkerboard-9x6"
    assert result.baseline_m == pytest.approx(0.07)
    assert result.views_used == 4
    assert list(result.translation_m) == pytest.approx([-0.07, 0.0, 0.0])
    assert len(result.rotation) == 9
    assert result.lens_model == survey_pb2.CALIBRATION_LENS_PINHOLE_RADTAN
    assert result.baseline_scale == pytest.approx(1.0)


async def test_an_expected_baseline_rescales_the_result_and_reports_the_implied_square() -> None:
    # Given a rig known to be 72.5 mm across, and a solve that reads 70 mm
    config = a_config(expected_baseline_m=0.0725)
    responses = await collect([config, *FOUR_DIVERSE_PAIRS, FINISH])

    # Then the result is rescaled and says what square size the solve implied
    result = responses[-1].result
    assert result.baseline_m == pytest.approx(0.0725)
    assert result.solved_baseline_m == pytest.approx(0.07)
    assert result.baseline_scale == pytest.approx(0.0725 / 0.07)
    assert result.implied_square_size_m == pytest.approx(0.025 * 0.0725 / 0.07)
    assert list(result.translation_m) == pytest.approx([-0.0725, 0.0, 0.0])


async def test_the_lens_model_and_detection_scale_reach_the_vision_adapter() -> None:
    # Given a fisheye stream that allows detection up to 2x upscaling
    detector = FakeDetector()
    config = a_config(lens_model=survey_pb2.CALIBRATION_LENS_FISHEYE, max_detection_scale=2)
    responses = await collect([config, *FOUR_DIVERSE_PAIRS, FINISH], detector)

    # Then detection and the solve were asked for exactly that
    assert set(detector.max_scales) == {2}
    assert detector.lenses == [LensModel.FISHEYE]
    assert responses[-1].result.lens_model == survey_pb2.CALIBRATION_LENS_FISHEYE


async def test_detection_defaults_to_no_upscaling() -> None:
    # Given a config that leaves the detection scale unset
    detector = FakeDetector()
    await collect([a_config(), a_pair(1)], detector)

    # Then detection runs at the native scale only
    assert set(detector.max_scales) == {1}


async def test_a_detection_scale_above_three_is_refused() -> None:
    # Given RTAB-Map's limit of 3x upscaling
    with pytest.raises(ValueError, match="max_detection_scale"):
        await collect([a_config(max_detection_scale=4)])


async def test_finishing_too_early_answers_not_ready_and_keeps_the_stream_open() -> None:
    # Given a finish after two views, then the rest of the views and a second finish
    items = [a_config(), a_pair(1), a_pair(2), FINISH, a_pair(3), a_pair(4), FINISH]
    responses = await collect(items)

    # Then the first finish is answered "not ready" and the second one solves
    kinds = [r.WhichOneof("kind") for r in responses]
    assert kinds == ["plan", "feedback", "feedback", "not_ready", "feedback", "feedback", "result"]
    assert responses[3].not_ready.accepted_views == 2
    assert "not ready" in responses[3].not_ready.message.lower()


async def test_an_unreadable_frame_is_reported_and_the_stream_continues() -> None:
    # Given a pair whose bytes cannot be decoded, followed by a good pair
    responses = await collect(
        [a_config(), a_pair(9), a_pair(1)], FakeDetector(unreadable=frozenset({9}))
    )

    # Then that pair is reported unreadable and the next one is still accepted
    assert responses[1].feedback.status == survey_pb2.CALIBRATION_VIEW_FRAME_UNREADABLE
    assert responses[2].feedback.status == survey_pb2.CALIBRATION_VIEW_ACCEPTED


async def test_a_frame_of_another_size_than_the_config_is_refused() -> None:
    # Given a 640x480 config and a 1280x720 pair
    with pytest.raises(ValueError, match="1280x720.*640x480"):
        await collect([a_config(), a_pair(1, width=1280, height=720)])


async def test_an_unset_config_size_is_taken_from_the_first_frame() -> None:
    # Given a config without a size and 1280x720 pairs
    responses = await collect([a_config(width=0, height=0), a_pair(1, width=1280, height=720)])

    # Then the plan waits for that size, and the board centre is
    # normalized over 1280x720, not a guessed 640x480
    assert [r.WhichOneof("kind") for r in responses] == ["plan", "feedback"]
    assert responses[1].feedback.board_center_x == pytest.approx(100 / 1280)


async def test_an_unspecified_target_is_refused() -> None:
    # Given a config with no explicit target type
    with pytest.raises(ValueError, match="checkerboard"):
        await collect([a_config(survey_pb2.CALIBRATION_TARGET_UNSPECIFIED)])


async def test_a_frame_before_config_is_refused() -> None:
    # Given a stream that opens with a frame
    with pytest.raises(ValueError, match="config"):
        await collect([a_pair(1)])


def test_the_calibration_service_is_a_bidi_stream_with_an_explicit_checkerboard_enum() -> None:
    # Given the generated survey bindings
    assert survey_pb2.CALIBRATION_TARGET_CHECKERBOARD == 1
    service = survey_pb2.DESCRIPTOR.services_by_name["CameraCalibrationService"]
    method = service.methods_by_name["StreamCalibration"]
    assert method.client_streaming and method.server_streaming


async def test_the_first_response_is_the_whole_capture_plan() -> None:
    # Given only a config
    responses = await collect([a_config()])

    # Then the server answers with every viewpoint the calibration needs
    plan = responses[0].plan
    assert len(plan.viewpoints) >= 9
    first = plan.viewpoints[0]
    assert first.index == 0
    assert first.target_cell == "centre"
    assert first.distance_m > 0 and first.board_size > 0
    assert first.instruction
    tilts = {v.tilt for v in plan.viewpoints}
    assert survey_pb2.CALIBRATION_TILT_TOP_RIGHT_AWAY in tilts


async def test_feedback_names_the_viewpoint_a_view_filled_and_what_remains() -> None:
    # Given a plan, and a small board near the upper-left of the image
    responses = await collect([a_config(), a_pair(1)])

    # Then the feedback names the far upper-left viewpoint and crosses it off
    plan, feedback = responses[0].plan, responses[1].feedback
    upper_left = next(v for v in plan.viewpoints if v.target_cell == "upper_left")
    assert feedback.matched_viewpoint == upper_left.index
    assert list(feedback.remaining_viewpoints) == [
        v.index for v in plan.viewpoints if v.index != upper_left.index
    ]
    assert feedback.suggestion.viewpoint_index in feedback.remaining_viewpoints
