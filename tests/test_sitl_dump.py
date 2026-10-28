"""ROS 2 SITL dumper helpers that do not need rclpy."""

from __future__ import annotations

import math

from surmap.simulation.sitl_dump import navsat_accuracy_m, take_stereo_pair


def test_navsat_accuracy_is_the_square_root_of_the_reported_variance() -> None:
    # Given a NavSatFix east-variance of 0.25 m²
    variance_m2 = 0.25

    # When the capture records horizontal accuracy
    accuracy_m = navsat_accuracy_m(variance_m2)

    # Then the value is in metres, not the covariance's square metres
    assert accuracy_m == 0.5


def test_a_non_positive_navsat_variance_falls_back_to_one_metre() -> None:
    # Given a fix that did not report a usable covariance
    # When accuracy is derived
    # Then the capture keeps the previous 1 m fallback
    assert navsat_accuracy_m(0.0) == 1.0
    assert navsat_accuracy_m(-4.0) == 1.0
    assert navsat_accuracy_m(math.nan) == 1.0


def test_unpaired_frames_older_than_twice_the_slop_are_dropped() -> None:
    # Given a left frame 100 ms older than the newest stamp, and a 20 ms slop
    left = {0: "old-left", 70_000_000: "recent-left"}
    right = {100_000_000: "right"}

    # When pairing runs
    pair = take_stereo_pair(left, right, slop_ns=20_000_000)

    # Then nothing pairs, and only the frame older than 40 ms is dropped
    assert pair is None
    assert 0 not in left
    assert left == {70_000_000: "recent-left"}
    assert right == {100_000_000: "right"}


def test_stamps_within_the_slop_become_one_stereo_pair() -> None:
    # Given a left and right stamp 10 ms apart, inside a 20 ms slop
    left = {1_000_000_000: "left"}
    right = {1_010_000_000: "right"}

    # When pairing runs
    pair = take_stereo_pair(left, right, slop_ns=20_000_000)

    # Then they leave the buffers as one pair keyed by the left stamp
    assert pair == (1_000_000_000, "left", "right")
    assert left == {}
    assert right == {}
