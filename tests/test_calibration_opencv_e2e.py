"""OpenCV sidecar over simulated checkerboard views (known truth)."""

import math

import pytest

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.opencv_sidecar import OpenCvSidecarVision
from surmap.calibration.plan import Tilt, Viewpoint
from surmap.calibration.port import CalibrationView, CornerSet, LensModel, StereoEstimate
from surmap.calibration.session import CalibrationSession
from surmap.calibration.simulated import BoardPose, RenderedPair, SimulatedCheckerboard

cv2 = pytest.importorskip("cv2")


def a_rig() -> SimulatedCheckerboard:
    return SimulatedCheckerboard(
        board=CheckerboardSpec(cols=9, rows=6, square_size_m=0.04),
        width=640,
        height=480,
        fx=381.36,
        fy=381.36,
        cx=320.0,
        cy=240.0,
        baseline_m=0.07,
    )


POSES = (
    BoardPose(z_m=0.8),
    BoardPose(x_m=-0.15, y_m=-0.08, z_m=1.0, yaw_deg=12.0),
    BoardPose(x_m=0.15, y_m=0.08, z_m=1.1, yaw_deg=-14.0, pitch_deg=8.0),
    BoardPose(x_m=-0.1, y_m=0.1, z_m=0.7, pitch_deg=-10.0, roll_deg=6.0),
    BoardPose(x_m=0.12, y_m=-0.1, z_m=1.3, yaw_deg=8.0, pitch_deg=-8.0),
    BoardPose(x_m=0.0, y_m=0.0, z_m=0.9, roll_deg=-8.0),
)


BOARD = CheckerboardSpec(9, 6, 0.04)
FAR_BOARD_Z_M = 4.5
"""Measured: 9x6 x 4 cm squares are about 3.4 px here; native detection misses them."""


def mean_error_px(found: CornerSet, truth: CornerSet) -> float:
    distances = [math.hypot(u - gu, v - gv) for (u, v), (gu, gv) in zip(found, truth, strict=True)]
    return sum(distances) / len(distances)


async def detect_both(
    vision: OpenCvSidecarVision,
    pair: RenderedPair,
    max_scale: int = 1,
    board: CheckerboardSpec = BOARD,
) -> CalibrationView:
    async def detect(data: bytes) -> CornerSet | None:
        return await vision.detect(
            frame_id=1,
            width=640,
            height=480,
            encoding="raw_rgb",
            data=data,
            board=board,
            max_scale=max_scale,
        )

    left, right = await detect(pair.left_rgb), await detect(pair.right_rgb)
    assert left is not None and right is not None
    return CalibrationView(left=left, right=right)


async def test_the_sidecar_finds_the_simulated_board() -> None:
    # Given one rendered pair
    pair = a_rig().render_pair(BoardPose(z_m=0.9))
    vision = OpenCvSidecarVision()
    try:
        # When the sidecar detects on the left eye
        corners = await vision.detect(
            frame_id=1,
            width=640,
            height=480,
            encoding="raw_rgb",
            data=pair.left_rgb,
            board=CheckerboardSpec(9, 6, 0.04),
            max_scale=1,
        )
    finally:
        await vision.close()

    # Then all 54 corners are found near the projected ground truth
    assert corners is not None and len(corners) == 54
    errors = [
        ((u - gu) ** 2 + (v - gv) ** 2) ** 0.5
        for (u, v), (gu, gv) in zip(corners, pair.left_corners, strict=True)
    ]
    # Corner order may start from either end of the board.
    errors_rev = [
        ((u - gu) ** 2 + (v - gv) ** 2) ** 0.5
        for (u, v), (gu, gv) in zip(corners, reversed(pair.left_corners), strict=True)
    ]
    assert min(sum(errors) / len(errors), sum(errors_rev) / len(errors_rev)) < 2.0


async def test_calibration_recovers_the_simulated_rig() -> None:
    # Given rendered views at diverse poses (ground-truth corners used
    # as the views, so this judges the solver, not the detector)
    rig = a_rig()
    board = CheckerboardSpec(9, 6, 0.04)
    views = tuple(
        CalibrationView(left=pair.left_corners, right=pair.right_corners)
        for pair in (rig.render_pair(p) for p in POSES)
    )
    vision = OpenCvSidecarVision()
    try:
        estimate = await vision.calibrate(
            views=views, board=board, width=640, height=480, lens=LensModel.PINHOLE_RADTAN
        )
    finally:
        await vision.close()

    # Then fx and baseline come back near the rig that rendered them
    assert estimate.left_fx == pytest.approx(381.36, rel=0.03)
    assert estimate.baseline_m == pytest.approx(0.07, rel=0.05)
    assert estimate.rms_stereo < 1.0


async def test_detected_corners_sit_within_a_quarter_pixel_of_the_rendered_truth() -> None:
    # Given a board facing the camera at 0.8 m
    pair = a_rig().render_pair(BoardPose(z_m=0.8))
    vision = OpenCvSidecarVision()
    try:
        # When both eyes are detected
        view = await detect_both(vision, pair)
    finally:
        await vision.close()

    # Then neither the renderer nor the detector biases the corners
    assert mean_error_px(view.left, pair.left_corners) < 0.25
    assert mean_error_px(view.right, pair.right_corners) < 0.25


async def test_a_small_far_board_keeps_its_corners_sub_pixel() -> None:
    # Given a tilted board at 1.3 m, its squares about 12 px wide
    pair = a_rig().render_pair(BoardPose(x_m=0.12, y_m=-0.1, z_m=1.3, yaw_deg=8.0, pitch_deg=-8.0))
    vision = OpenCvSidecarVision()
    try:
        # When the left eye is detected
        view = await detect_both(vision, pair)
    finally:
        await vision.close()

    # Then refinement did not pull corners onto their neighbours
    assert mean_error_px(view.left, pair.left_corners) < 0.3


async def test_calibration_from_detected_corners_recovers_the_simulated_rig() -> None:
    # Given the detector's own corners for rendered views at diverse poses
    rig = a_rig()
    vision = OpenCvSidecarVision()
    try:
        views = tuple([await detect_both(vision, rig.render_pair(p)) for p in POSES])

        # When those detections are solved
        estimate = await vision.calibrate(
            views=views, board=BOARD, width=640, height=480, lens=LensModel.PINHOLE_RADTAN
        )
    finally:
        await vision.close()

    # Then the whole pipeline, not just the solver, recovers the rig
    assert estimate.left_fx == pytest.approx(381.36, rel=0.02)
    assert estimate.right_fx == pytest.approx(381.36, rel=0.02)
    assert estimate.baseline_m == pytest.approx(0.07, rel=0.03)
    assert estimate.translation_m[0] == pytest.approx(-0.07, rel=0.03)
    assert len(estimate.distortion_left) == 4


WIDE_POSES = (
    *POSES,
    BoardPose(x_m=-0.22, y_m=-0.14, z_m=0.75, yaw_deg=20.0, pitch_deg=-12.0),
    BoardPose(x_m=0.22, y_m=0.14, z_m=0.75, yaw_deg=-20.0, pitch_deg=12.0),
    BoardPose(x_m=0.22, y_m=-0.14, z_m=0.8, yaw_deg=-16.0, pitch_deg=-10.0),
    BoardPose(x_m=-0.22, y_m=0.14, z_m=0.8, yaw_deg=16.0, pitch_deg=10.0),
)
"""Views reaching the image corners, where lens distortion lives."""

BARREL = (-0.25, 0.07, 0.001, -0.001)
"""A typical small-camera radial-tangential lens (k1, k2, p1, p2)."""


def a_distorted_rig(
    lens: LensModel, distortion: tuple[float, ...], fx: float
) -> SimulatedCheckerboard:
    return SimulatedCheckerboard(
        board=BOARD,
        width=640,
        height=480,
        fx=fx,
        fy=fx,
        cx=320.0,
        cy=240.0,
        baseline_m=0.07,
        lens=lens,
        distortion=distortion,
    )


async def solve_detected(rig: SimulatedCheckerboard, lens: LensModel) -> StereoEstimate:
    vision = OpenCvSidecarVision()
    try:
        views = tuple([await detect_both(vision, rig.render_pair(p)) for p in WIDE_POSES])
        return await vision.calibrate(views=views, board=BOARD, width=640, height=480, lens=lens)
    finally:
        await vision.close()


async def test_a_radial_tangential_lens_is_recovered_with_its_distortion() -> None:
    # Given a barrel-distorted rig, solved with the default pinhole model
    rig = a_distorted_rig(LensModel.PINHOLE_RADTAN, BARREL, fx=381.36)
    estimate = await solve_detected(rig, LensModel.PINHOLE_RADTAN)

    # Then focal length, baseline and the main radial term come back
    assert estimate.left_fx == pytest.approx(381.36, rel=0.02)
    assert estimate.baseline_m == pytest.approx(0.07, rel=0.03)
    assert estimate.distortion_left[0] == pytest.approx(-0.25, abs=0.03)


async def test_the_rational_model_solves_a_distorted_rig_with_eight_coefficients() -> None:
    # Given the same rig, solved with RTAB-Map's rational model
    rig = a_distorted_rig(LensModel.PINHOLE_RADTAN, BARREL, fx=381.36)
    estimate = await solve_detected(rig, LensModel.PINHOLE_RATIONAL)

    # Then the rig is recovered and the eight rational coefficients returned
    assert estimate.lens is LensModel.PINHOLE_RATIONAL
    assert estimate.left_fx == pytest.approx(381.36, rel=0.02)
    assert estimate.baseline_m == pytest.approx(0.07, rel=0.03)
    assert len(estimate.distortion_left) == 8


async def test_the_fisheye_model_recovers_a_wide_fisheye_rig() -> None:
    # Given an equidistant fisheye rig with a wide field of view
    rig = a_distorted_rig(LensModel.FISHEYE, (0.08, -0.02, 0.005, 0.0), fx=260.0)
    estimate = await solve_detected(rig, LensModel.FISHEYE)

    # Then the fisheye solve recovers it, with the four fisheye coefficients
    assert estimate.lens is LensModel.FISHEYE
    assert estimate.left_fx == pytest.approx(260.0, rel=0.02)
    assert estimate.baseline_m == pytest.approx(0.07, rel=0.03)
    assert len(estimate.distortion_left) == 4


FAR_POSE = BoardPose(x_m=0.0, y_m=0.0, z_m=FAR_BOARD_Z_M)


async def test_a_board_too_small_at_native_scale_is_found_by_upscaling() -> None:
    # Given a board so far away that native-scale detection misses it
    pair = a_rig().render_pair(FAR_POSE)
    vision = OpenCvSidecarVision()
    try:
        native = await vision.detect(
            frame_id=1, width=640, height=480, encoding="raw_rgb",
            data=pair.left_rgb, board=BOARD, max_scale=1,
        )  # fmt: skip
        # When up to 2x upscaling is allowed
        upscaled = await detect_both(vision, pair, max_scale=2)
    finally:
        await vision.close()

    # Then it is found, with corners back in native pixels
    assert native is None
    assert mean_error_px(upscaled.left, pair.left_corners) < 0.3


_AWAY_SIGNS = {
    Tilt.TOP_LEFT_AWAY: (-1, -1),
    Tilt.TOP_RIGHT_AWAY: (1, -1),
    Tilt.BOTTOM_LEFT_AWAY: (-1, 1),
    Tilt.BOTTOM_RIGHT_AWAY: (1, 1),
}


def pose_following(viewpoint: Viewpoint, *, fx: float, baseline_m: float) -> BoardPose:
    """Where a person following `viewpoint`'s instruction puts the board.

    They match its apparent size under the real lens (so its distance
    scales with the true focal length, not the plan's nominal one) and
    centre it midway between the lenses.
    """
    distance = viewpoint.distance_m * fx / 640
    half_angle = math.radians(viewpoint.tilt_deg / math.sqrt(2))
    sx, sy = _AWAY_SIGNS.get(viewpoint.tilt, (0, 0))
    return BoardPose(
        x_m=(viewpoint.center_x - 0.5) * 640 * distance / fx + baseline_m / 2,
        y_m=(viewpoint.center_y - 0.5) * 480 * distance / fx,
        z_m=distance,
        yaw_deg=-math.degrees(half_angle) * sx,
        pitch_deg=math.degrees(half_angle) * sy,
    )


@pytest.mark.parametrize("fx", [300.0, 381.36, 520.0])
async def test_following_the_capture_plan_makes_the_session_ready_and_solves_the_rig(
    fx: float,
) -> None:
    # Given a rig whose focal length the plan does not know
    board = CheckerboardSpec(9, 6, 0.025)
    rig = SimulatedCheckerboard(
        board=board, width=640, height=480, fx=fx, fy=fx, cx=320.0, cy=240.0, baseline_m=0.07
    )
    session = CalibrationSession(board=board, width=640, height=480, min_views=9)
    vision = OpenCvSidecarVision()
    try:
        # When one view is taken per planned viewpoint, as instructed
        for viewpoint in session.plan:
            pair = rig.render_pair(pose_following(viewpoint, fx=fx, baseline_m=0.07))
            view = await detect_both(vision, pair, board=board)
            session.observe(frame_id=viewpoint.index, left=view.left, right=view.right)
        estimate = await vision.calibrate(
            views=session.views, board=board, width=640, height=480, lens=session.lens
        )
    finally:
        await vision.close()

    # Then every viewpoint was filled, RTAB-Map's bar is cleared, and the rig comes back
    assert session.remaining_viewpoints == ()
    assert session.ready
    assert estimate.left_fx == pytest.approx(fx, rel=0.02)
    assert estimate.baseline_m == pytest.approx(0.07, rel=0.03)
