"""Demo fusion: SAM masks claim stereo points, RTAB-Map poses place them.

A local stand-in for the base station's `surmap_fuse` step
(`docs/architecture.md` §5: masks × cloud × RTAB-Map pose).

Frames: stereo points are optical camera frame (x right, y down,
z forward); the RTAB-Map sidecar's poses are its base frame (x
forward, y left, z up). `camera_to_base` is RTAB-Map's EuRoC
convention, `B · T_BS(cam0)`, where `T_BS` is the camera→IMU
calibration from `sensor.yaml` and `B` the base←IMU rotation. A
point reaches the map in two `to_map_frame` hops: camera → base via
that mount, base → map via the keyframe's pose.

The semantic layer is its own layer over RTAB-Map's output: nothing
here is fed back into RTAB-Map, and only frames RTAB-Map posed are
placed (an unposed frame is never given a guessed pose).
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray

from surmap.demo.datasets import DemoCalibration
from surmap.geometry import to_map_frame
from surmap.types import Pose, Vec3

# RTAB-Map's EuRoC base frame from the EuRoC IMU frame (x up → z up).
_BASE_FROM_IMU = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])

MAX_SEMANTIC_POINTS = 600


def _quaternion_xyzw(rotation: NDArray[np.float64]) -> tuple[float, float, float, float]:
    trace = float(np.trace(rotation))
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (rotation[2, 1] - rotation[1, 2]) / s
        y = (rotation[0, 2] - rotation[2, 0]) / s
        z = (rotation[1, 0] - rotation[0, 1]) / s
    elif rotation[0, 0] > rotation[1, 1] and rotation[0, 0] > rotation[2, 2]:
        s = math.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2.0
        w = (rotation[2, 1] - rotation[1, 2]) / s
        x = 0.25 * s
        y = (rotation[0, 1] + rotation[1, 0]) / s
        z = (rotation[0, 2] + rotation[2, 0]) / s
    elif rotation[1, 1] > rotation[2, 2]:
        s = math.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2.0
        w = (rotation[0, 2] - rotation[2, 0]) / s
        x = (rotation[0, 1] + rotation[1, 0]) / s
        y = 0.25 * s
        z = (rotation[1, 2] + rotation[2, 1]) / s
    else:
        s = math.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2.0
        w = (rotation[1, 0] - rotation[0, 1]) / s
        x = (rotation[0, 2] + rotation[2, 0]) / s
        y = (rotation[1, 2] + rotation[2, 1]) / s
        z = 0.25 * s
    return (float(x), float(y), float(z), float(w))


def camera_to_base(cam0_yaml: str) -> Pose:
    """The optical camera's pose in RTAB-Map's EuRoC base frame."""
    match = re.search(r"T_BS:.*?data: \[([^\]]+)\]", cam0_yaml, re.S)
    if match is None:
        raise ValueError("cam0 sensor.yaml has no T_BS")
    t_bs = np.array([float(value) for value in match.group(1).split(",")]).reshape(4, 4)
    rotation = _BASE_FROM_IMU @ t_bs[:3, :3]
    if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-3) or np.linalg.det(rotation) < 0:
        raise ValueError("cam0 T_BS rotation is not a proper rotation")
    x, y, z = (float(value) for value in _BASE_FROM_IMU @ t_bs[:3, 3])
    return Pose(Vec3(x, y, z), _quaternion_xyzw(rotation))


def points_in_mask(
    points: Sequence[Vec3],
    mask: NDArray[np.bool_],
    calibration: DemoCalibration,
    *,
    max_depth_m: float = 6.0,
) -> tuple[Vec3, ...]:
    """The camera-frame points whose pixel lies inside `mask`."""
    height, width = mask.shape
    claimed: list[Vec3] = []
    for point in points:
        if point.z <= 0.05 or point.z > max_depth_m:
            continue
        u = calibration.fx * point.x / point.z + calibration.cx
        v = calibration.fy * point.y / point.z + calibration.cy
        if 0.0 <= u < width and 0.0 <= v < height and mask[int(v), int(u)]:
            claimed.append(point)
    return tuple(claimed)


class SemanticSummary(TypedDict):
    label: str
    count: int
    frames: int
    xy: list[list[float]]


class SemanticLayer:
    """Map-frame object points per label, placed by RTAB-Map poses."""

    def __init__(self, mount: Pose) -> None:
        self._mount = mount
        self._points: dict[str, list[Vec3]] = {}
        self._frames: dict[str, set[int]] = {}

    def add(self, label: str, *, frame_id: int, points_camera: Sequence[Vec3], pose: Pose) -> None:
        placed = [to_map_frame(to_map_frame(point, self._mount), pose) for point in points_camera]
        self._points.setdefault(label, []).extend(placed)
        self._frames.setdefault(label, set()).add(frame_id)

    def summary(self, max_points: int = MAX_SEMANTIC_POINTS) -> list[SemanticSummary]:
        """Per label: exact counts and an evenly sampled XY set to draw."""
        entries: list[SemanticSummary] = []
        for label in sorted(self._points):
            points = self._points[label]
            sample = points
            if len(sample) > max_points:
                step = len(sample) / max_points
                sample = [sample[int(index * step)] for index in range(max_points)]
            entries.append(
                SemanticSummary(
                    label=label,
                    count=len(points),
                    frames=len(self._frames[label]),
                    xy=[[round(point.x, 3), round(point.y, 3)] for point in sample],
                )
            )
        return entries
