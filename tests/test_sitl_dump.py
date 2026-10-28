"""ROS 2 SITL dumper helpers that do not need rclpy."""

from __future__ import annotations

import math

from surmap.simulation.sitl_dump import navsat_accuracy_m


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
