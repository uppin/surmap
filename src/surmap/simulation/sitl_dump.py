"""Pure helpers for the ROS 2 SITL capture dumper.

The dumper itself (`scripts/ros2/dump_sitl_capture.py`) runs under a
ROS-sourced interpreter. These functions stay free of rclpy so the
capture rules can be tested with the rest of SurMap.
"""

from __future__ import annotations

import math


def navsat_accuracy_m(variance_m2: float) -> float:
    """Horizontal accuracy in metres from a NavSatFix variance (m²).

    `sensor_msgs/NavSatFix.position_covariance` is in metres squared.
    A non-positive or non-finite variance (the common all-zero report)
    falls back to 1 m.
    """
    if not math.isfinite(variance_m2) or variance_m2 <= 0.0:
        return 1.0
    return math.sqrt(variance_m2)
