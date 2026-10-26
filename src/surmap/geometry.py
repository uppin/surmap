"""Camera-frame to map-frame point transforms."""

from __future__ import annotations

from surmap.types import Pose, Vec3


def _rotate(v: Vec3, q: tuple[float, float, float, float]) -> Vec3:
    x, y, z, w = q
    # v' = v + 2 * cross(q_xyz, cross(q_xyz, v) + w * v)
    cx = y * v.z - z * v.y + w * v.x
    cy = z * v.x - x * v.z + w * v.y
    cz = x * v.y - y * v.x + w * v.z
    return Vec3(
        v.x + 2.0 * (y * cz - z * cy),
        v.y + 2.0 * (z * cx - x * cz),
        v.z + 2.0 * (x * cy - y * cx),
    )


def to_map_frame(point_camera: Vec3, pose: Pose) -> Vec3:
    """Transform one camera-frame point into the map frame using a pose."""
    r = _rotate(point_camera, pose.orientation_xyzw)
    p = pose.position
    return Vec3(r.x + p.x, r.y + p.y, r.z + p.z)


def centroid(points: tuple[Vec3, ...]) -> Vec3:
    if not points:
        raise ValueError("centroid of an empty point set is undefined")
    n = float(len(points))
    return Vec3(
        sum(p.x for p in points) / n,
        sum(p.y for p in points) / n,
        sum(p.z for p in points) / n,
    )
