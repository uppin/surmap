"""EuRoC dataset text shared by the RTAB-Map sidecar and the SITL export.

`rtabmap-euroc_dataset` reads `mav0/imu0/data.csv` (it skips the header
line) and does not require `cam0`/`cam1` `data.csv`: image stamps come
from the filenames in `mav0/camN/data/`.
"""

from __future__ import annotations

from collections.abc import Sequence

from surmap.types import StereoFramePair

_IMU_HEADER = "#timestamp [ns],w_RS_S_x,w_RS_S_y,w_RS_S_z,a_RS_S_x,a_RS_S_y,a_RS_S_z"
_IMU_PERIOD_NS = 5_000_000  # 200 Hz


def stationary_imu_csv(frames: Sequence[StereoFramePair]) -> str:
    """A stationary-IMU CSV covering `frames` (the dataset tool needs one).

    Samples run at 200 Hz from the first frame's stamp through the last.
    Specific force is +9.81 m/s² on body X: in the EuRoC IMU frame +X is
    up when the vehicle is level, which is the axis the dataset tool's
    fixed `baseToImu` rotation expects for a hover.
    """
    if not frames:
        return _IMU_HEADER + "\n"
    rows = [_IMU_HEADER]
    start, end = frames[0].t_ns, frames[-1].t_ns
    t_ns = start
    while t_ns <= end:
        rows.append(f"{t_ns},0.0,0.0,0.0,9.81,0.0,0.0")
        t_ns += _IMU_PERIOD_NS
    return "\n".join(rows) + "\n"
