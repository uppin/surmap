"""Machine 3 helpers: Gazebo/PX4 SITL capture → SurMap EuRoC sessions.

SurMap stays passive: this package never sends flight commands. PX4
(or a human) flies; SurMap only converts sensor dumps into the same
session shape a real CM5 recording would produce.
"""

from surmap.simulation.calibration import StereoCalibrationSpec, render_cam_sensor_yaml
from surmap.simulation.disaster_world import (
    DisasterGroundTruth,
    enu_to_wgs84,
    load_disaster_ground_truth,
    load_survey_plan,
)
from surmap.simulation.euroc_export import ExportResult, export_euroc_session
from surmap.simulation.sitl_capture import load_sitl_capture

__all__ = [
    "DisasterGroundTruth",
    "ExportResult",
    "StereoCalibrationSpec",
    "enu_to_wgs84",
    "export_euroc_session",
    "load_disaster_ground_truth",
    "load_sitl_capture",
    "load_survey_plan",
    "render_cam_sensor_yaml",
]
