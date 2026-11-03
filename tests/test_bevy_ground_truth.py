"""Ground-truth geometry: the left eye in ENU and a box on its image."""

import math

import pytest
from surmap.simulation.bevy_ground_truth import left_eye_optical_pose, project_box
from surmap.simulation.bevy_wire import GroundTruthBox

from surmap.simulation.calibration import StereoCalibrationSpec
from surmap.types import Pose, Vec3

HALF_SQRT2 = math.sqrt(2.0) / 2.0


def a_calibration() -> StereoCalibrationSpec:
    return StereoCalibrationSpec(
        calibration_id="bevy-sitl-poc-v1",
        width=640,
        height=480,
        fx=381.36,
        fy=381.36,
        cx=320.0,
        cy=240.0,
        baseline_m=0.07,
        rate_hz=10.0,
    )


def a_north_facing_rig(position: Vec3) -> Pose:
    # Forward-left-up to ENU for a north-facing rig is a +90 degree turn about up.
    return Pose(position, (0.0, 0.0, HALF_SQRT2, HALF_SQRT2))


def polygon_centroid(polygon: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    return (
        sum(point[0] for point in polygon) / len(polygon),
        sum(point[1] for point in polygon) / len(polygon),
    )


def test_the_left_eye_sits_half_a_baseline_along_rig_left_from_the_rig_centre() -> None:
    # Given a north-facing rig centred at (10, 20, 5) in ENU, whose left is west
    rig = a_north_facing_rig(Vec3(10.0, 20.0, 5.0))

    # When the left eye's optical pose is derived
    eye = left_eye_optical_pose(rig, a_calibration())

    # Then the eye is half a baseline west of the centre, at the same height
    assert eye.position.x == pytest.approx(10.0 - 0.035)
    assert eye.position.y == pytest.approx(20.0)
    assert eye.position.z == pytest.approx(5.0)


def test_the_left_eye_optical_axes_point_right_down_and_forward() -> None:
    # Given the same north-facing rig
    rig = a_north_facing_rig(Vec3(0.0, 0.0, 5.0))

    # When the left eye's optical pose is derived
    eye = left_eye_optical_pose(rig, a_calibration())

    # Then its orientation is the -90 degree turn about east that takes the
    # forward-left-up frame to right-down-forward (quaternion up to sign)
    expected = (-HALF_SQRT2, 0.0, 0.0, HALF_SQRT2)
    dot = sum(a * b for a, b in zip(eye.orientation_xyzw, expected, strict=True))
    assert abs(dot) == pytest.approx(1.0)


def test_a_box_straight_ahead_projects_to_a_polygon_around_the_image_centre() -> None:
    # Given a north-facing rig and a box ten metres ahead of it
    rig = a_north_facing_rig(Vec3(0.0, 0.0, 1.0))
    box = GroundTruthBox(
        id="car-1", kind="car", min_enu=Vec3(-1.0, 10.0, 0.0), max_enu=Vec3(1.0, 12.0, 2.0)
    )

    # When the box is projected onto the left image
    polygon = project_box(box, rig, a_calibration())

    # Then a convex polygon of at least four corners surrounds the principal point
    assert len(polygon) >= 4
    centroid_x, centroid_y = polygon_centroid(polygon)
    assert centroid_x == pytest.approx(320.0, abs=40.0)
    assert centroid_y == pytest.approx(240.0, abs=40.0)


def test_a_box_behind_the_camera_projects_to_no_polygon() -> None:
    # Given a north-facing rig and a box ten metres behind it
    rig = a_north_facing_rig(Vec3(0.0, 0.0, 1.0))
    box = GroundTruthBox(
        id="car-1", kind="car", min_enu=Vec3(-1.0, -12.0, 0.0), max_enu=Vec3(1.0, -10.0, 2.0)
    )

    # When the box is projected onto the left image
    polygon = project_box(box, rig, a_calibration())

    # Then there is nothing to draw
    assert polygon == ()
