"""Project map-frame tracks and detector boxes onto the camera frame."""

from __future__ import annotations

import math

from surmap.detection.tracker import TrackedDetection
from surmap.geometry import to_camera_frame, to_map_frame
from surmap.types import Pose, Vec3
from surmap.viewer.model import CameraModel, Overlay, PlacedTrack

_MIN_BOX_PX = 16.0


def track_overlays(
    pose: Pose, placed: tuple[PlacedTrack, ...], camera: CameraModel
) -> tuple[Overlay, ...]:
    """Boxes and mask outlines for tracks in front of the camera."""
    overlays = []
    for item in placed:
        if not item.visible:
            continue
        overlay = _track_overlay(pose, item, camera)
        if overlay is not None:
            overlays.append(overlay)
    return tuple(overlays)


def detection_overlays(
    pose: Pose,
    detections: tuple[TrackedDetection, ...],
    camera_points: tuple[Vec3, ...],
    camera: CameraModel,
) -> tuple[Overlay, ...]:
    """Detector boxes. A confident box is static; a weak one is unknown."""
    overlays = []
    for detection in detections:
        depth = _depth_in_box(detection.box_xyxy, camera_points, camera)
        label = detection.label.upper()
        if depth is not None:
            label = f"{label} {depth:.1f} m"
        motion = "static" if detection.score >= 0.5 else "unknown"
        overlays.append(
            Overlay(
                xyxy=detection.box_xyxy,
                label=label,
                motion=motion,
                track_id=f"det-{detection.track_id}",
                mask=(),
            )
        )
    return tuple(overlays)


def map_points(pose: Pose, camera_points: tuple[Vec3, ...], limit: int) -> tuple[Vec3, ...]:
    """Camera-frame scene points in the map frame, evenly sampled."""
    sampled = _sample(camera_points, limit)
    return tuple(to_map_frame(point, pose) for point in sampled)


def _track_overlay(pose: Pose, item: PlacedTrack, camera: CameraModel) -> Overlay | None:
    projected = _project(item.xyz, pose, camera)
    if projected is None:
        return None
    u, v, depth = projected
    if not _inside(u, v, camera):
        return None
    polygon = _mask_polygon(pose, item, camera)
    if len(polygon) < 3:
        polygon = _billboard(pose, item, camera)
    if len(polygon) < 3:
        polygon = _minimum_box(u, v, camera)
    box = _bounds(polygon)
    box = _enforce_min_size(box, u, v)
    label = f"{item.track.label.upper()} {depth:.1f} m"
    return Overlay(box, label, item.track.motion, item.track.id, polygon)


def _mask_polygon(
    pose: Pose, item: PlacedTrack, camera: CameraModel
) -> tuple[tuple[float, float], ...]:
    if not item.track.mask_points:
        return ()
    pixels = []
    for point in item.track.mask_points:
        projected = _project(point, pose, camera)
        if projected is None:
            continue
        u, v, _depth = projected
        pixels.append((u, v))
    return _convex_hull(pixels)


def _billboard(
    pose: Pose, item: PlacedTrack, camera: CameraModel
) -> tuple[tuple[float, float], ...]:
    width_m, height_m = _extent(item.track.label)
    right = to_map_frame(Vec3(1.0, 0.0, 0.0), Pose(Vec3(0.0, 0.0, 0.0), pose.orientation_xyzw))
    right = _unit(right)
    up = Vec3(0.0, 0.0, 1.0)
    center = item.xyz
    half_w = width_m / 2.0
    half_h = height_m / 2.0
    corners = (
        _add(center, _add(_scale(right, half_w), _scale(up, half_h))),
        _add(center, _add(_scale(right, -half_w), _scale(up, half_h))),
        _add(center, _add(_scale(right, -half_w), _scale(up, -half_h))),
        _add(center, _add(_scale(right, half_w), _scale(up, -half_h))),
    )
    pixels = []
    for corner in corners:
        projected = _project(corner, pose, camera)
        if projected is None:
            return ()
        pixels.append((projected[0], projected[1]))
    return tuple(pixels)


def _extent(label: str) -> tuple[float, float]:
    key = label.lower()
    if "person" in key:
        return (0.6, 1.75)
    if "car" in key or "vehicle" in key:
        return (1.8, 1.4)
    if "roof" in key or "building" in key:
        return (2.4, 1.6)
    return (1.0, 0.8)


def _project(point: Vec3, pose: Pose, camera: CameraModel) -> tuple[float, float, float] | None:
    local = to_camera_frame(point, pose)
    if local.z <= 0.25:
        return None
    u = camera.fx * local.x / local.z + camera.cx
    v = camera.fy * local.y / local.z + camera.cy
    return (u, v, local.z)


def _depth_in_box(
    box: tuple[float, float, float, float],
    camera_points: tuple[Vec3, ...],
    camera: CameraModel,
) -> float | None:
    depths = []
    for point in camera_points:
        if point.z <= 0.25:
            continue
        u = camera.fx * point.x / point.z + camera.cx
        v = camera.fy * point.y / point.z + camera.cy
        if box[0] <= u <= box[2] and box[1] <= v <= box[3]:
            depths.append(point.z)
    if not depths:
        return None
    depths.sort()
    return depths[len(depths) // 2]


def _inside(u: float, v: float, camera: CameraModel) -> bool:
    return 0.0 <= u < camera.width and 0.0 <= v < camera.height


def _bounds(points: tuple[tuple[float, float], ...]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _enforce_min_size(
    box: tuple[float, float, float, float], u: float, v: float
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    if x2 - x1 >= _MIN_BOX_PX and y2 - y1 >= _MIN_BOX_PX:
        return box
    half_w = max(_MIN_BOX_PX, x2 - x1) / 2.0
    half_h = max(_MIN_BOX_PX, y2 - y1) / 2.0
    return (u - half_w, v - half_h, u + half_w, v + half_h)


def _minimum_box(u: float, v: float, camera: CameraModel) -> tuple[tuple[float, float], ...]:
    del camera
    half_w = _MIN_BOX_PX / 2.0
    half_h = _MIN_BOX_PX
    return (
        (u - half_w, v - half_h),
        (u + half_w, v - half_h),
        (u + half_w, v + half_h),
        (u - half_w, v + half_h),
    )


def _convex_hull(points: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    unique = sorted(set(points))
    if len(unique) < 3:
        return tuple(unique)

    def cross(origin: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return tuple(lower[:-1] + upper[:-1])


def _sample(points: tuple[Vec3, ...], limit: int) -> tuple[Vec3, ...]:
    if limit <= 0 or len(points) <= limit:
        return points
    step = len(points) / limit
    return tuple(points[int(index * step)] for index in range(limit))


def _add(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x + b.x, a.y + b.y, a.z + b.z)


def _scale(point: Vec3, factor: float) -> Vec3:
    return Vec3(point.x * factor, point.y * factor, point.z * factor)


def _unit(point: Vec3) -> Vec3:
    norm = math.sqrt(point.x**2 + point.y**2 + point.z**2)
    if norm == 0.0:
        return Vec3(1.0, 0.0, 0.0)
    return _scale(point, 1.0 / norm)
