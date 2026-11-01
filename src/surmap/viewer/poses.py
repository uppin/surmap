"""Map-frame poses. x east, y north, z up, matching the snapshot."""

from __future__ import annotations

import math

from surmap.geometry import to_map_frame
from surmap.types import Pose, Vec3

# Same metre-per-degree the snapshot writer documents.
METRES_PER_DEGREE = 111_320.0


def enu_offset(
    origin_lat: float, origin_lon: float, origin_alt: float, lat: float, lon: float, alt: float
) -> Vec3:
    """Metres east/north/up from a WGS84 origin. Same scale as the snapshot."""
    lat_rad = math.radians(origin_lat)
    east = (lon - origin_lon) * METRES_PER_DEGREE * math.cos(lat_rad)
    north = (lat - origin_lat) * METRES_PER_DEGREE
    return Vec3(east, north, alt - origin_alt)


def camera_pose(position: Vec3, yaw_rad: float, pitch_down_rad: float) -> Pose:
    """Camera pose. Yaw 0 looks north. Pitch 0 is level. Optical axis is +Z."""
    forward = (
        math.sin(yaw_rad) * math.cos(pitch_down_rad),
        math.cos(yaw_rad) * math.cos(pitch_down_rad),
        -math.sin(pitch_down_rad),
    )
    right = (math.cos(yaw_rad), -math.sin(yaw_rad), 0.0)
    # down = -(right × forward), so image +Y is world-down when the camera is level.
    cross = (
        right[1] * forward[2] - right[2] * forward[1],
        right[2] * forward[0] - right[0] * forward[2],
        right[0] * forward[1] - right[1] * forward[0],
    )
    down = (-cross[0], -cross[1], -cross[2])
    rotation = (
        (right[0], down[0], forward[0]),
        (right[1], down[1], forward[1]),
        (right[2], down[2], forward[2]),
    )
    return Pose(position, _mat_to_quat(rotation))


def compose_camera_pose(
    body: Pose,
    rotation: tuple[
        tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]
    ],
    translation: tuple[float, float, float],
) -> Pose:
    """Camera pose from a body pose and a camera-to-body `T_BS`."""
    q_bs = _mat_to_quat(rotation)
    orientation = _quat_mul(body.orientation_xyzw, q_bs)
    rotated = to_map_frame(Vec3(*translation), Pose(Vec3(0.0, 0.0, 0.0), body.orientation_xyzw))
    position = Vec3(
        rotated.x + body.position.x,
        rotated.y + body.position.y,
        rotated.z + body.position.z,
    )
    return Pose(position, _normalize(orientation))


def _mat_to_quat(
    rotation: tuple[
        tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]
    ],
) -> tuple[float, float, float, float]:
    m00, m01, m02 = rotation[0]
    m10, m11, m12 = rotation[1]
    m20, m21, m22 = rotation[2]
    trace = m00 + m11 + m22
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        return ((m21 - m12) / scale, (m02 - m20) / scale, (m10 - m01) / scale, 0.25 * scale)
    if m00 > m11 and m00 > m22:
        scale = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        return (0.25 * scale, (m01 + m10) / scale, (m02 + m20) / scale, (m21 - m12) / scale)
    if m11 > m22:
        scale = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        return ((m01 + m10) / scale, 0.25 * scale, (m12 + m21) / scale, (m02 - m20) / scale)
    scale = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
    return ((m02 + m20) / scale, (m12 + m21) / scale, 0.25 * scale, (m10 - m01) / scale)


def _quat_mul(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _normalize(q: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    norm = math.sqrt(sum(part * part for part in q))
    if norm == 0.0:
        return (0.0, 0.0, 0.0, 1.0)
    return (q[0] / norm, q[1] / norm, q[2] / norm, q[3] / norm)
