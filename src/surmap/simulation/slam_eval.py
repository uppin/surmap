"""Judging RTAB-Map's output against the simulation's perfect ground truth.

A position fit (`trajectory_eval.align_rigid`) leaves the roll about a
near-straight path unconstrained and hides drift by spreading it. Here
the map is anchored once, from one camera pose pair — RTAB-Map's
rectified left camera in its map frame and the true left optical camera
in ENU for the same frame — and never re-fitted: what remains at the end
of a closed loop is drift, and dense points can be judged against the
true surfaces exactly.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from surmap.simulation.trajectory_eval import RigidAlignment
from surmap.types import Pose

Points = NDArray[np.float64]


def _rotation(pose: Pose) -> NDArray[np.float64]:
    x, y, z, w = pose.orientation_xyzw
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _position(pose: Pose) -> NDArray[np.float64]:
    return np.array([pose.position.x, pose.position.y, pose.position.z], dtype=np.float64)


def anchor_map_to_enu(camera_in_map: Pose, camera_in_enu: Pose) -> RigidAlignment:
    """The map → ENU transform that puts the estimated camera on the true one."""
    rotation = _rotation(camera_in_enu) @ _rotation(camera_in_map).T
    translation = _position(camera_in_enu) - rotation @ _position(camera_in_map)
    return RigidAlignment(rotation=rotation, translation=translation)


def in_camera_frame(points_in_map: Points, camera_in_map: Pose) -> Points:
    """Map-frame points in the camera's own (optical) frame."""
    local: Points = (points_in_map - _position(camera_in_map)) @ _rotation(camera_in_map)
    return local


def track_drift(estimate_in_map: Points, truth_in_enu: Points, anchor: RigidAlignment) -> Points:
    """Per-frame distance (m) between the anchored estimate and the truth."""
    if estimate_in_map.shape != truth_in_enu.shape:
        raise ValueError("estimate and truth must pair frame for frame")
    drift: Points = np.linalg.norm(anchor.apply(estimate_in_map) - truth_in_enu, axis=1)
    return drift
