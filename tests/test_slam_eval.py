"""Judging RTAB-Map against a perfect world: one anchor, never re-fitted."""

import numpy as np
import pytest

from surmap.simulation.slam_eval import anchor_map_to_enu, in_camera_frame, track_drift
from surmap.types import Pose, Vec3

# A quarter turn about up: map x is ENU north.
QUARTER_TURN_Z = (0.0, 0.0, float(np.sin(np.pi / 4)), float(np.cos(np.pi / 4)))


def a_camera_in_map() -> Pose:
    return Pose(Vec3(1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0))


def the_same_camera_in_enu() -> Pose:
    return Pose(Vec3(10.0, 20.0, 5.0), QUARTER_TURN_Z)


def test_one_camera_pose_pair_anchors_the_map_in_enu() -> None:
    # Given RTAB-Map's camera pose and the true camera pose for one frame
    anchor = anchor_map_to_enu(a_camera_in_map(), the_same_camera_in_enu())

    # When the camera's own position and a point 1 m along map x are mapped
    mapped = anchor.apply(np.array([[1.0, 2.0, 3.0], [2.0, 2.0, 3.0]]))

    # Then the camera lands on its true position and map x points north
    np.testing.assert_allclose(mapped, [[10.0, 20.0, 5.0], [10.0, 21.0, 5.0]], atol=1e-9)


def test_points_one_metre_ahead_of_a_camera_are_at_depth_one() -> None:
    # Given a camera at the map origin looking down its own +z (optical frame)
    camera = Pose(Vec3(0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))

    # When a map point 1 m in front of it is put into the camera frame
    local = in_camera_frame(np.array([[0.0, 0.0, 1.0]]), camera)

    # Then it is straight ahead at depth 1
    np.testing.assert_allclose(local, [[0.0, 0.0, 1.0]], atol=1e-9)


def test_a_track_matching_the_truth_has_no_drift() -> None:
    # Given an estimated track that is the true one seen from another frame
    truth = np.array([[10.0, 20.0, 5.0], [10.0, 21.0, 5.0], [9.0, 22.0, 5.0]])
    estimate = np.array([[1.0, 2.0, 3.0], [2.0, 2.0, 3.0], [3.0, 3.0, 3.0]])
    anchor = anchor_map_to_enu(a_camera_in_map(), the_same_camera_in_enu())

    # When drift is measured against the truth through the start anchor alone
    drift = track_drift(estimate, truth, anchor)

    # Then every frame is where it should be
    np.testing.assert_allclose(drift, [0.0, 0.0, 0.0], atol=1e-9)


def test_drift_is_the_distance_left_after_the_start_anchor() -> None:
    # Given an estimate whose last frame is 0.5 m short along map x
    truth = np.array([[10.0, 20.0, 5.0], [10.0, 22.0, 5.0]])
    estimate = np.array([[1.0, 2.0, 3.0], [2.5, 2.0, 3.0]])
    anchor = anchor_map_to_enu(a_camera_in_map(), the_same_camera_in_enu())

    # When drift is measured
    drift = track_drift(estimate, truth, anchor)

    # Then the end is 0.5 m off and the anchored start is exact
    assert drift.tolist() == pytest.approx([0.0, 0.5])
