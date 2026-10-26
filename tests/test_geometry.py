import pytest

from surmap.geometry import centroid, to_map_frame
from surmap.types import Pose, Vec3


def test_identity_pose_translates_only() -> None:
    pose = Pose(Vec3(1.0, 2.0, 3.0))
    assert to_map_frame(Vec3(0.5, 0.0, 0.0), pose) == Vec3(1.5, 2.0, 3.0)


def test_z_up_quarter_turn_rotation() -> None:
    # 90 degrees about Z: quaternion (0, 0, sin45, cos45); x axis -> y axis.
    s = 2**0.5 / 2.0
    pose = Pose(Vec3(0.0, 0.0, 0.0), (0.0, 0.0, s, s))
    out = to_map_frame(Vec3(1.0, 0.0, 0.0), pose)
    assert out.x == pytest.approx(0.0)
    assert out.y == pytest.approx(1.0)
    assert out.z == pytest.approx(0.0)


def test_centroid_and_empty_error() -> None:
    assert centroid((Vec3(0, 0, 0), Vec3(2, 2, 2))) == Vec3(1, 1, 1)
    with pytest.raises(ValueError):
        centroid(())
