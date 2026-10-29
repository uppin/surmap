"""A SAM polygon claims camera-frame cloud points and poses them."""

from surmap.survey.mask_cloud import points_in_mask
from surmap.survey.stereo import StereoRig
from surmap.types import Pose, Vec3


def _rig() -> StereoRig:
    return StereoRig(fx=100.0, fy=100.0, cx=50.0, cy=40.0, baseline_m=0.12)


def _square() -> tuple[tuple[float, float], ...]:
    return ((20.0, 10.0), (80.0, 10.0), (80.0, 70.0), (20.0, 70.0))


def test_square_mask_returns_only_the_inside_point_translated_by_the_pose() -> None:
    # Given three camera points, one of which projects inside a square mask
    rig = _rig()
    outside = Vec3(0.45, 0.0, 1.0)  # pixel (95, 40), in frame, outside the square
    too_close = Vec3(0.0, 0.0, 0.05)  # would land on (50, 40), but z <= 0.05
    inside = Vec3(0.0, 0.0, 2.0)  # pixel (50, 40)
    pose = Pose(Vec3(10.0, 20.0, 30.0))

    # When the mask claims points from the cloud
    claimed = points_in_mask(
        (outside, too_close, inside),
        rig,
        _square(),
        120,
        80,
        pose,
    )

    # Then only the inside point remains, translated by the pose
    assert claimed == (Vec3(10.0, 20.0, 32.0),)


def test_empty_polygon_returns_an_empty_tuple() -> None:
    # Given a point that would otherwise project inside the frame
    rig = _rig()
    pose = Pose(Vec3(10.0, 0.0, 0.0))

    # When the mask polygon is empty
    claimed = points_in_mask((Vec3(0.0, 0.0, 2.0),), rig, (), 120, 80, pose)

    # Then the mask claims nothing
    assert claimed == ()


def test_point_projecting_outside_the_frame_is_not_claimed() -> None:
    # Given a polygon larger than the frame and a point that projects past its right edge
    rig = _rig()
    covering = ((-10.0, -10.0), (200.0, -10.0), (200.0, 200.0), (-10.0, 200.0))
    past_the_frame = Vec3(1.0, 0.0, 1.0)  # pixel (150, 40); width is 120
    inside_the_frame = Vec3(0.0, 0.0, 1.0)  # pixel (50, 40)

    # When the mask is applied at the frame size
    claimed = points_in_mask(
        (past_the_frame, inside_the_frame),
        rig,
        covering,
        120,
        80,
        Pose(Vec3(0.0, 0.0, 0.0)),
    )

    # Then only the point that lands on a frame pixel is kept
    assert claimed == (Vec3(0.0, 0.0, 1.0),)


def test_kept_point_stays_in_the_camera_frame_when_no_pose_is_passed() -> None:
    # Given one point inside the square and no pose
    rig = _rig()
    inside = Vec3(0.0, 0.0, 2.0)

    # When the mask claims it
    claimed = points_in_mask((inside,), rig, _square(), 120, 80)

    # Then the point is unchanged, still in the camera frame
    assert claimed == (inside,)
