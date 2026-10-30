"""Z-buffer projection. The unbuffered mask claim is left as it is."""

from __future__ import annotations

from surmap.segbench.project import project_mask
from surmap.survey.mask_cloud import points_in_mask
from surmap.survey.stereo import StereoRig
from surmap.types import Pose, Vec3

_RIG = StereoRig(fx=10.0, fy=10.0, cx=4.0, cy=4.0, baseline_m=0.1)
_FULL = ((0.0, 0.0), (8.0, 0.0), (8.0, 8.0), (0.0, 8.0))
_NEAR = Vec3(0.0, 0.0, 2.0)
_FAR = Vec3(0.0, 0.0, 5.0)


def test_points_in_mask_also_claims_the_background_point_behind_the_subject() -> None:
    # Given a near point and a farther point on the same pixel, both inside the mask
    points = (_NEAR, _FAR)

    # When the existing projection runs, with no z-buffer
    claimed = points_in_mask(points, _RIG, _FULL, 8, 8)

    # Then both depths are kept
    assert len(claimed) == 2
    assert claimed[0].z == 2.0
    assert claimed[1].z == 5.0


def test_the_z_buffer_keeps_only_the_nearer_point_on_a_shared_pixel() -> None:
    # Given the same pair, the farther point sitting behind the subject
    points = (_NEAR, _FAR)

    # When the occlusion-aware projection runs
    claimed = project_mask(points, _RIG, _FULL, 8, 8)

    # Then the mask claims the subject and not the background behind it
    assert len(claimed) == 1
    assert claimed[0].z == 2.0


def test_an_equal_depth_keeps_the_earlier_point() -> None:
    # Given two points at the same depth on one pixel
    first = Vec3(0.0, 0.0, 2.0)
    second = Vec3(0.0, 0.0, 2.0)

    # When they are projected
    claimed = project_mask((first, second), _RIG, _FULL, 8, 8)

    # Then one point remains
    assert len(claimed) == 1
    assert claimed[0].z == 2.0


def test_a_pose_places_the_winning_point_in_the_map_frame() -> None:
    # Given a camera whose map position is 10 m east of the origin
    pose = Pose(Vec3(10.0, 0.0, 0.0))

    # When the nearer point is projected with that pose
    claimed = project_mask((_NEAR, _FAR), _RIG, _FULL, 8, 8, pose)

    # Then the map point is the camera point plus that translation
    assert len(claimed) == 1
    assert claimed[0].x == 10.0
    assert claimed[0].y == 0.0
    assert claimed[0].z == 2.0


def test_an_empty_polygon_claims_no_points() -> None:
    # Given a cloud and a ring that is not a mask
    # When it is projected
    claimed = project_mask((_NEAR,), _RIG, ((1.0, 1.0), (2.0, 2.0)), 8, 8)

    # Then nothing is claimed
    assert claimed == ()
