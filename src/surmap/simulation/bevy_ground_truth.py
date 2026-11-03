"""Ground-truth geometry: the left eye in ENU and a box on its image."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from surmap.simulation.bevy_wire import GroundTruthBox
from surmap.simulation.calibration import StereoCalibrationSpec
from surmap.types import Pose, Vec3

Quat = tuple[float, float, float, float]
Vec = tuple[float, float, float]


def _rotate(q: Quat, v: Vec) -> Vec:
    x, y, z, w = q
    # v + 2 * cross(q_xyz, cross(q_xyz, v) + w*v)
    cx = y * v[2] - z * v[1] + w * v[0]
    cy = z * v[0] - x * v[2] + w * v[1]
    cz = x * v[1] - y * v[0] + w * v[2]
    return (
        v[0] + 2.0 * (y * cz - z * cy),
        v[1] + 2.0 * (z * cx - x * cz),
        v[2] + 2.0 * (x * cy - y * cx),
    )


def _mul(a: Quat, b: Quat) -> Quat:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _conjugate(q: Quat) -> Quat:
    return (-q[0], -q[1], -q[2], q[3])


# Rotation taking optical coordinates (right, down, forward) into the
# rig's forward-left-up frame: forward -> FLU x, right -> -FLU y, down -> -FLU z.
# It is a -90 degree turn about the forward axis composed as the cyclic
# permutation below; its quaternion is derived from that matrix.
def _optical_to_flu() -> Quat:
    # Matrix (optical -> FLU) columns: right=(0,-1,0), down=(0,0,-1), forward=(1,0,0).
    # Trace = -1, use the standard largest-diagonal branch via matrix conversion.
    m = ((0.0, 0.0, 1.0), (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0))  # rows
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2.0
        return (
            (m[2][1] - m[1][2]) / s,
            (m[0][2] - m[2][0]) / s,
            (m[1][0] - m[0][1]) / s,
            0.25 * s,
        )
    if m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        return (
            0.25 * s,
            (m[0][1] + m[1][0]) / s,
            (m[0][2] + m[2][0]) / s,
            (m[2][1] - m[1][2]) / s,
        )
    if m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        return (
            (m[0][1] + m[1][0]) / s,
            0.25 * s,
            (m[1][2] + m[2][1]) / s,
            (m[0][2] - m[2][0]) / s,
        )
    s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
    return (
        (m[0][2] + m[2][0]) / s,
        (m[1][2] + m[2][1]) / s,
        0.25 * s,
        (m[1][0] - m[0][1]) / s,
    )


def left_eye_optical_pose(rig: Pose, calibration: StereoCalibrationSpec) -> Pose:
    q = rig.orientation_xyzw
    left = _rotate(q, (0.0, 1.0, 0.0))
    half = calibration.baseline_m / 2.0
    position = Vec3(
        rig.position.x + left[0] * half,
        rig.position.y + left[1] * half,
        rig.position.z + left[2] * half,
    )
    orientation = _mul(q, _optical_to_flu())
    return Pose(position, orientation)


def _box_corners(box: GroundTruthBox) -> list[Vec]:
    lo, hi = box.min_enu, box.max_enu
    return [(x, y, z) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]


_EDGES = (
    (0, 1),
    (0, 2),
    (0, 4),
    (1, 3),
    (1, 5),
    (2, 3),
    (2, 6),
    (3, 7),
    (4, 5),
    (4, 6),
    (5, 7),
    (6, 7),
)


def _hull(points: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    unique = sorted(set(points))
    if len(unique) < 3:
        return ()

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    hull = lower[:-1] + upper[:-1]
    return tuple(hull) if len(hull) >= 3 else ()


def project_box(
    box: GroundTruthBox, rig: Pose, calibration: StereoCalibrationSpec
) -> tuple[tuple[float, float], ...]:
    eye = left_eye_optical_pose(rig, calibration)
    inverse = _conjugate(eye.orientation_xyzw)

    def to_camera(point: Vec) -> Vec:
        delta = (
            point[0] - eye.position.x,
            point[1] - eye.position.y,
            point[2] - eye.position.z,
        )
        return _rotate(inverse, delta)

    corners = [to_camera(corner) for corner in _box_corners(box)]
    near = 1e-6
    projected: list[tuple[float, float]] = []

    def add(point: Vec) -> None:
        if point[2] > near:
            projected.append(
                (
                    calibration.fx * point[0] / point[2] + calibration.cx,
                    calibration.fy * point[1] / point[2] + calibration.cy,
                )
            )

    for start_index, end_index in _EDGES:
        start, end = corners[start_index], corners[end_index]
        add(start)
        # Clip the edge against the near plane and add the crossing.
        if (start[2] - near) * (end[2] - near) < 0:
            fraction = (near - start[2]) / (end[2] - start[2])
            crossing = tuple(start[i] + fraction * (end[i] - start[i]) for i in range(3))
            add((crossing[0], crossing[1], crossing[2]))
    return _hull(projected)


def box_surface_distance(points: NDArray[np.float64], box: GroundTruthBox) -> NDArray[np.float64]:
    """Distance (m) of each ENU point to the surface of an axis-aligned box.

    Zero on a face; inside the box it is the depth to the nearest face, so
    a reconstruction of a solid object is judged by how close its points
    lie to the object's skin.
    """
    lo = np.array([box.min_enu.x, box.min_enu.y, box.min_enu.z])
    hi = np.array([box.max_enu.x, box.max_enu.y, box.max_enu.z])
    centre, half = (lo + hi) / 2.0, (hi - lo) / 2.0
    q = np.abs(points - centre) - half
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
    inside = np.minimum(q.max(axis=1), 0.0)
    return np.asarray(outside + np.abs(inside), dtype=np.float64)
