"""The capture plan: every viewpoint a calibration needs, known up front."""

import pytest

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.plan import Tilt, capture_plan
from surmap.calibration.port import CornerSet, LensModel
from surmap.calibration.session import CalibrationSession, ViewStatus
from tests.calibration_builders import a_detection, shifted, width_for

BOARD = CheckerboardSpec(cols=9, rows=6, square_size_m=0.025)


def a_session(min_views: int = 9) -> CalibrationSession:
    return CalibrationSession(board=BOARD, width=640, height=480, min_views=min_views)


def observe(session: CalibrationSession, frame_id: int, left: CornerSet) -> int:
    """Observe a stereo pair; the planned viewpoint it filled, or -1."""
    feedback = session.observe(frame_id=frame_id, left=left, right=shifted(left, -27))
    assert feedback.status is ViewStatus.ACCEPTED
    return feedback.matched_viewpoint


def test_the_plan_spans_rtab_maps_readiness_bar_in_position_size_and_tilt() -> None:
    # When a plan is made for a 640x480 pinhole stream
    plan = capture_plan(BOARD, width=640, height=480, lens=LensModel.PINHOLE_RADTAN)

    # Then its targets alone would clear x, y > 0.5 and size > 0.4
    xs = [v.center_x for v in plan]
    ys = [v.center_y for v in plan]
    sizes = [v.board_size for v in plan]
    assert max(xs) - min(xs) > 0.5
    assert max(ys) - min(ys) > 0.5
    assert max(sizes) - min(sizes) > 0.4
    # And it asks for each corner of the board turned away (RTAB-Map's
    # skew is a corner angle, which a diagonal tilt is what changes)
    assert {v.tilt for v in plan} >= {
        Tilt.TOP_LEFT_AWAY,
        Tilt.TOP_RIGHT_AWAY,
        Tilt.BOTTOM_LEFT_AWAY,
        Tilt.BOTTOM_RIGHT_AWAY,
    }
    assert [v.index for v in plan] == list(range(len(plan)))


def test_every_viewpoint_names_a_distance_and_an_instruction() -> None:
    # When a plan is made
    plan = capture_plan(BOARD, width=640, height=480, lens=LensModel.PINHOLE_RADTAN)

    # Then a farther viewpoint is a smaller board, and each one says what to do
    near = max(plan, key=lambda v: v.board_size)
    far = min(plan, key=lambda v: v.board_size)
    assert far.distance_m > near.distance_m > 0
    assert all(v.instruction for v in plan)


def test_a_session_starts_with_every_viewpoint_remaining() -> None:
    # Given a fresh session
    session = a_session()

    # Then the whole plan remains and the suggestion is its first viewpoint
    assert session.remaining_viewpoints == tuple(v.index for v in session.plan)
    feedback = session.observe(frame_id=1, left=None, right=None)
    assert feedback.suggestion.viewpoint_index == session.plan[0].index


def test_a_view_that_fills_a_planned_viewpoint_is_matched_and_crossed_off() -> None:
    # Given the plan's far upper-left viewpoint
    session = a_session()
    target = next(v for v in session.plan if v.target_cell == "upper_left")
    width_px = width_for(target.board_size)

    # When a flat board is seen there at that size
    matched = observe(session, 1, a_detection(640 / 6, 480 / 6, width_px=width_px))

    # Then that viewpoint is matched and no longer remaining
    assert matched == target.index
    assert target.index not in session.remaining_viewpoints


def test_a_tilt_is_matched_by_which_corner_is_turned_away() -> None:
    # Given the plan's viewpoint with the board's top-right corner turned away
    session = a_session()
    target = next(v for v in session.plan if v.tilt is Tilt.TOP_RIGHT_AWAY)
    cx, cy = target.center_x * 640, target.center_y * 480
    width_px = width_for(target.board_size)

    # When the opposite corner is turned away first, then the right one
    wrong = observe(session, 1, a_detection(cx, cy, width_px=width_px, away="bottom_left"))
    right = observe(session, 2, a_detection(cx, cy, width_px=width_px, away="top_right"))

    # Then only the matching corner fills it — even though RTAB-Map's
    # unsigned skew alone would call the two views alike
    assert wrong != target.index
    assert right == target.index


def test_a_view_matching_no_remaining_viewpoint_is_still_kept() -> None:
    # Given a board at a spot the plan never asks for
    session = a_session()

    # When it is seen
    matched = observe(session, 1, a_detection(430, 160, width_px=200, shear=0.2))

    # Then it is kept for the solve but fills no viewpoint
    assert matched == -1
    assert len(session.views) == 1


def test_after_a_match_the_suggestion_moves_to_the_next_remaining_viewpoint() -> None:
    # Given the first planned viewpoint filled
    session = a_session()
    first = session.plan[0]
    width_px = width_for(first.board_size)
    cx, cy = first.center_x * 640, first.center_y * 480
    feedback = session.observe(
        frame_id=1,
        left=a_detection(cx, cy, width_px=width_px),
        right=shifted(a_detection(cx, cy, width_px=width_px), -27),
    )

    # Then the next suggestion is the next viewpoint of the plan
    assert feedback.matched_viewpoint == first.index
    assert feedback.suggestion.viewpoint_index == session.plan[1].index


@pytest.mark.parametrize("lens", list(LensModel))
def test_every_lens_model_gets_a_plan(lens: LensModel) -> None:
    assert capture_plan(BOARD, width=640, height=480, lens=lens)
