"""Demo fusion tests: SAM masks claim stereo points, RTAB-Map poses place them.

Frames: stereo points are optical camera frame (x right, y down,
z forward); RTAB-Map poses are base frame (x forward, y left, z up).
`camera_to_base` is RTAB-Map's EuRoC convention, `B · T_BS(cam0)`.
"""

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.demo.datasets import DemoCalibration
from surmap.demo.fusion import SemanticLayer, camera_to_base, points_in_mask
from surmap.geometry import to_map_frame
from surmap.types import Pose, Vec3


# EuRoC's cam0 mount, rounded: camera x → IMU y, camera y → IMU -x.
def cam0_yaml(translation: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> str:
    x, y, z = translation
    return f"""sensor_type: camera
T_BS:
  cols: 4
  rows: 4
  data: [0.0, -1.0, 0.0, {x},
         1.0, 0.0, 0.0, {y},
         0.0, 0.0, 1.0, {z},
         0.0, 0.0, 0.0, 1.0]
resolution: [376, 240]
intrinsics: [10.0, 10.0, 10.0, 10.0]
"""


def is_near(actual: Vec3, expected: Vec3, metres: float = 1e-6) -> bool:
    return (
        abs(actual.x - expected.x) <= metres
        and abs(actual.y - expected.y) <= metres
        and abs(actual.z - expected.z) <= metres
    )


def a_calibration() -> DemoCalibration:
    return DemoCalibration(fx=10.0, fy=10.0, cx=10.0, cy=10.0, baseline_m=0.1, width=20, height=20)


def left_half_mask() -> NDArray[np.bool_]:
    mask = np.zeros((20, 20), dtype=bool)
    mask[:, :10] = True
    return mask


def test_straight_ahead_of_the_camera_is_straight_ahead_of_the_base() -> None:
    # Given EuRoC's camera mount
    mount = camera_to_base(cam0_yaml())

    # When a point 2 m along the optical axis is moved into the base frame
    point = to_map_frame(Vec3(0.0, 0.0, 2.0), mount)

    # Then it is 2 m forward of the base
    assert is_near(point, Vec3(2.0, 0.0, 0.0))


def test_camera_right_and_down_are_base_right_and_down() -> None:
    # Given the same mount
    mount = camera_to_base(cam0_yaml())

    # When points to the camera's right and below it are moved into the base frame
    right = to_map_frame(Vec3(1.0, 0.0, 0.0), mount)
    down = to_map_frame(Vec3(0.0, 1.0, 0.0), mount)

    # Then right is base -y and down is base -z
    assert is_near(right, Vec3(0.0, -1.0, 0.0))
    assert is_near(down, Vec3(0.0, 0.0, -1.0))


def test_the_camera_mount_offset_is_carried_into_the_base_frame() -> None:
    # Given EuRoC's mount, offset 5 cm along the IMU's y axis
    mount = camera_to_base(cam0_yaml((0.0, 0.05, 0.0)))

    # When the camera origin is moved into the base frame
    origin = to_map_frame(Vec3(0.0, 0.0, 0.0), mount)

    # Then it sits at that offset, rotated by the base convention
    assert is_near(origin, Vec3(0.0, -0.05, 0.0))


def test_a_degenerate_mount_rotation_is_rejected() -> None:
    zero_rotation = cam0_yaml().replace("0.0, -1.0, 0.0,", "0.0, 0.0, 0.0,", 1)
    with pytest.raises(ValueError, match="rotation"):
        camera_to_base(zero_rotation)


def test_only_points_projecting_inside_the_mask_are_claimed() -> None:
    # Given a mask over the left half of a 20x20 frame
    left = Vec3(-0.5, 0.0, 1.0)  # projects to u = 5
    right = Vec3(0.5, 0.0, 1.0)  # projects to u = 15

    # When both points are tested against the mask
    claimed = points_in_mask((left, right), left_half_mask(), a_calibration())

    # Then only the left point is claimed
    assert claimed == (left,)


def test_points_behind_the_camera_or_too_far_are_never_claimed() -> None:
    # Given points that would project into the mask but are behind or far
    behind = Vec3(0.5, 0.0, -1.0)
    far = Vec3(-5.0, 0.0, 10.0)

    # When they are tested with a 6 m depth limit
    claimed = points_in_mask((behind, far), left_half_mask(), a_calibration(), max_depth_m=6.0)

    # Then neither is claimed
    assert claimed == ()


def test_a_segment_lands_in_the_map_through_the_mount_and_the_rtabmap_pose() -> None:
    # Given a base posed 10 m forward in the map, EuRoC camera mount
    layer = SemanticLayer(camera_to_base(cam0_yaml()))

    # When a chair point 2 m ahead of the camera is added
    layer.add(
        "chair", frame_id=21, points_camera=(Vec3(0.0, 0.0, 2.0),), pose=Pose(Vec3(10.0, 0.0, 0.0))
    )

    # Then the chair is 12 m forward in the map
    (chair,) = layer.summary()
    assert chair["label"] == "chair"
    assert chair["count"] == 1
    assert chair["xy"] == [[12.0, 0.0]]


def test_the_layer_counts_frames_and_points_per_label() -> None:
    # Given a layer
    layer = SemanticLayer(camera_to_base(cam0_yaml()))
    pose = Pose(Vec3(0.0, 0.0, 0.0))

    # When chairs are seen in two frames and a person in one
    layer.add("chair", frame_id=1, points_camera=(Vec3(0, 0, 1), Vec3(0, 0, 2)), pose=pose)
    layer.add("chair", frame_id=21, points_camera=(Vec3(0, 0, 3),), pose=pose)
    layer.add("person", frame_id=21, points_camera=(Vec3(0, 0, 1),), pose=pose)

    # Then the summary has each label once, with its point and frame counts
    summary = {entry["label"]: entry for entry in layer.summary()}
    assert summary["chair"]["count"] == 3
    assert summary["chair"]["frames"] == 2
    assert summary["person"]["count"] == 1


def test_the_drawn_sample_is_bounded() -> None:
    # Given a layer holding many chair points
    layer = SemanticLayer(camera_to_base(cam0_yaml()))
    points = tuple(Vec3(0.0, 0.0, 1.0 + index * 0.01) for index in range(500))
    layer.add("chair", frame_id=1, points_camera=points, pose=Pose(Vec3(0.0, 0.0, 0.0)))

    # When it is summarised with a 100-point budget
    (chair,) = layer.summary(max_points=100)

    # Then the count is exact but only 100 points are drawn
    assert chair["count"] == 500
    assert len(chair["xy"]) == 100
