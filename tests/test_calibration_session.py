"""Calibration session: feedback, coverage and next-pose guidance."""

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.port import CornerSet, LensModel
from surmap.calibration.session import CalibrationSession, ViewFeedback, ViewStatus
from tests.calibration_builders import DIVERSE_VIEWS, a_detection, shifted, width_for


def a_session(min_views: int = 3, lens: LensModel = LensModel.PINHOLE_RADTAN) -> CalibrationSession:
    return CalibrationSession(
        board=CheckerboardSpec(cols=9, rows=6, square_size_m=0.025),
        width=640,
        height=480,
        min_views=min_views,
        lens=lens,
    )


def corners_at(cx: float, cy: float, half: float = 40.0) -> tuple[tuple[float, float], ...]:
    """A fake 54-corner detection centred at (cx, cy)."""
    pts = []
    for r in range(6):
        for c in range(9):
            pts.append((cx - half + c * half / 4, cy - half / 2 + r * half / 5))
    return tuple(pts)


def observe_all(session: CalibrationSession, views: tuple[CornerSet, ...]) -> ViewFeedback:
    """Observe each left-eye view as a stereo pair; the last feedback."""
    feedbacks = [
        session.observe(frame_id=frame_id, left=left, right=shifted(left, -27))
        for frame_id, left in enumerate(views, start=1)
    ]
    return feedbacks[-1]


FLAT_CORNER_VIEWS = tuple(
    a_detection(cx, cy) for cx, cy in ((100, 80), (540, 80), (100, 400), (540, 400))
)
"""All four image corners, all facing the camera at one distance."""


def test_a_missing_board_is_reported_and_the_centre_is_suggested_first() -> None:
    # Given a fresh session
    session = a_session()

    # When no board is seen in either eye
    feedback = session.observe(frame_id=1, left=None, right=None)

    # Then it says so and asks for a centred board
    assert feedback.status is ViewStatus.BOARD_NOT_FOUND
    assert feedback.accepted_views == 0
    assert feedback.suggestion.target_cell == "centre"
    assert "centre" in feedback.suggestion.instruction.lower()


def test_a_view_filling_the_centre_viewpoint_moves_the_suggestion_elsewhere() -> None:
    # Given the plan's near, centred viewpoint filled
    session = a_session()
    near = a_detection(320, 240, width_px=width_for(session.plan[0].board_size))
    session.observe(frame_id=1, left=near, right=shifted(near, -27))

    # When the next suggestion is read
    feedback = session.observe(frame_id=2, left=None, right=None)

    # Then another viewpoint is requested
    assert feedback.suggestion.target_cell != "centre"
    assert feedback.coverage_fraction > 0.0


def test_a_near_duplicate_view_is_rejected_as_too_similar() -> None:
    # Given the same board position twice
    session = a_session()
    first = session.observe(frame_id=1, left=corners_at(320, 240), right=corners_at(293, 240))
    second = session.observe(frame_id=2, left=corners_at(322, 241), right=corners_at(295, 241))

    # Then only the first is accepted
    assert first.status is ViewStatus.ACCEPTED
    assert second.status is ViewStatus.TOO_SIMILAR
    assert second.accepted_views == 1


def test_views_in_one_eye_only_are_not_accepted() -> None:
    # Given a board seen on the left only
    session = a_session()

    # When observed
    feedback = session.observe(frame_id=1, left=corners_at(320, 240), right=None)

    # Then it is not a stereo view
    assert feedback.status is ViewStatus.BOARD_NOT_FOUND
    assert feedback.left_found and not feedback.right_found
    assert feedback.accepted_views == 0


def test_the_session_is_ready_once_views_span_position_size_and_tilt() -> None:
    # Given views spread across the image, near and far, flat and tilted
    session = a_session(min_views=4)

    # When they are observed
    last = observe_all(session, DIVERSE_VIEWS)

    # Then every spread clears RTAB-Map's bar and it is ready to solve
    assert last.accepted_views == 4
    assert last.x_spread > 0.5 and last.y_spread > 0.5
    assert last.size_spread > 0.4 and last.skew_spread > 0.5
    assert last.ready
    assert last.suggestion.target_cell == "done"


def test_many_flat_views_of_one_size_are_never_ready_and_ask_for_tilt() -> None:
    # Given views in all four corners, all facing the camera at one distance
    session = a_session(min_views=4)

    # When they are observed
    last = observe_all(session, FLAT_CORNER_VIEWS)

    # Then position is covered, but without tilt it is not ready
    assert last.accepted_views == 4
    assert last.x_spread > 0.5 and last.y_spread > 0.5
    assert not last.ready
    assert "tilt" in last.suggestion.instruction.lower()


def test_a_right_eye_detection_in_reverse_order_is_reordered_to_match_the_left() -> None:
    # Given a right-eye detection that starts from the board's far corner
    session = a_session()
    left = a_detection(320, 240)
    right = shifted(left, -27)

    # When the pair is observed
    feedback = session.observe(frame_id=1, left=left, right=tuple(reversed(right)))

    # Then the kept view pairs corner i in both eyes
    assert feedback.status is ViewStatus.ACCEPTED
    assert session.views[0].right == right


MODERATE_DEPTH_VIEWS = (
    a_detection(100, 80, width_px=120),
    a_detection(540, 400, width_px=120, shear=0.35),
    a_detection(320, 240, width_px=360),
    a_detection(320, 240, width_px=360, shear=0.35),
)
"""Spread in position and tilt, but size only about 0.34 apart."""


def test_a_pinhole_session_needs_more_size_spread_than_moderate_depths_give() -> None:
    # Given a pinhole session (RTAB-Map's size bar: 0.4)
    session = a_session(min_views=4)

    # Then a size spread of about 0.34 is not enough
    assert not observe_all(session, MODERATE_DEPTH_VIEWS).ready


def test_a_fisheye_session_is_ready_with_rtab_maps_relaxed_size_spread() -> None:
    # Given a fisheye session (RTAB-Map relaxes the size bar to 0.25)
    session = a_session(min_views=4, lens=LensModel.FISHEYE)

    # Then the same views are enough
    assert observe_all(session, MODERATE_DEPTH_VIEWS).ready
