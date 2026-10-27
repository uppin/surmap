"""Machine 3 helpers: Gazebo/PX4 SITL capture → SurMap EuRoC sessions.

SurMap stays passive: this package never sends flight commands. PX4
(or a human) flies; SurMap only converts sensor dumps into the same
session shape a real CM5 recording would produce.
"""

from surmap.simulation.calibration import StereoCalibrationSpec, render_cam_sensor_yaml
from surmap.simulation.euroc_export import ExportResult, export_euroc_session
from surmap.simulation.sitl_capture import load_sitl_capture

__all__ = [
    "ExportResult",
    "StereoCalibrationSpec",
    "export_euroc_session",
    "load_sitl_capture",
    "render_cam_sensor_yaml",
]
