"""Simulated checkerboard: known rig + board pose -> stereo pair."""

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.simulated import BoardPose, SimulatedCheckerboard


def a_board() -> CheckerboardSpec:
    return CheckerboardSpec(cols=9, rows=6, square_size_m=0.025)


def a_rig() -> SimulatedCheckerboard:
    return SimulatedCheckerboard(
        board=a_board(),
        width=640,
        height=480,
        fx=381.36,
        fy=381.36,
        cx=320.0,
        cy=240.0,
        baseline_m=0.07,
    )


def test_the_board_object_points_form_a_flat_grid() -> None:
    # Given a 9x6 inner-corner board with 25 mm squares
    board = a_board()

    # Then object points lie on Z=0 spaced by the square size
    points = board.object_points()
    assert len(points) == 54
    assert points[0] == (0.0, 0.0, 0.0)
    assert points[1] == (0.025, 0.0, 0.0)
    assert points[9] == (0.0, 0.025, 0.0)


def test_a_centred_board_projects_inside_both_eyes() -> None:
    # Given a board 1 m ahead, centred
    rig = a_rig()

    # When its corners are projected
    left, right = rig.project_corners(BoardPose(z_m=1.0))

    # Then every corner lands inside the 640x480 image in both eyes
    for corners in (left, right):
        assert len(corners) == 54
        assert all(0.0 <= u < 640 and 0.0 <= v < 480 for u, v in corners)


def test_the_right_eye_sees_the_board_shifted_by_the_baseline_disparity() -> None:
    # Given a board 1 m ahead
    rig = a_rig()

    # When projected into both eyes
    left, right = rig.project_corners(BoardPose(z_m=1.0))

    # Then right corners sit fx*baseline/z pixels left of the left ones
    expected = 381.36 * 0.07 / 1.0
    shifts = [lu - ru for (lu, _), (ru, _) in zip(left, right, strict=True)]
    assert all(abs(s - expected) < 1e-6 for s in shifts)


def test_a_rendered_pair_carries_the_projected_board() -> None:
    # Given a board ahead and slightly yawed
    rig = a_rig()

    # When a stereo pair is rendered
    pair = rig.render_pair(BoardPose(z_m=0.9, yaw_deg=15.0))

    # Then both frames are full-size raw RGB and the board covers part of the left image
    assert (pair.width, pair.height) == (640, 480)
    assert len(pair.left_rgb) == 640 * 480 * 3
    assert len(pair.right_rgb) == 640 * 480 * 3
    assert 0.02 < pair.left_board_fraction < 0.9
