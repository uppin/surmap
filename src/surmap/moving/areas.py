"""Stage 2: moving areas - mask, polygon, area tracks (design step 2)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from surmap.moving.candidates import CandidateCluster
from surmap.moving.config import MovingConfig

Polygon = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class AreaObservation:
    """One moving area on one frame."""

    frame_id: int
    polygon: Polygon
    depth_min_m: float
    depth_max_m: float
    point_count: int


@dataclass
class AreaTrack:
    """An area associated across frames."""

    track_id: int
    last_frame_id: int
    observation_count: int
    centroid: tuple[float, float] = (0.0, 0.0)


def _point_line_distance(
    point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    ax, ay = a
    bx, by = b
    px, py = point
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify_polygon(polygon: Polygon, epsilon_px: float, config: MovingConfig) -> Polygon:
    """Douglas-Peucker simplification, capped at config.max_polygon_vertices."""
    if len(polygon) <= 2:
        return polygon
    keep = [False] * len(polygon)
    keep[0] = keep[-1] = True
    stack = [(0, len(polygon) - 1)]
    points = list(polygon)
    while stack:
        first, last = stack.pop()
        farthest, farthest_dist = -1, -1.0
        for index in range(first + 1, last):
            dist = _point_line_distance(points[index], points[first], points[last])
            if dist > farthest_dist:
                farthest, farthest_dist = index, dist
        if farthest >= 0 and farthest_dist > epsilon_px:
            keep[farthest] = True
            stack.append((first, farthest))
            stack.append((farthest, last))
    simplified = tuple(point for point, kept in zip(points, keep, strict=True) if kept)
    cap = config.max_polygon_vertices
    if len(simplified) > cap:
        step = len(simplified) / cap
        simplified = tuple(simplified[int(i * step)] for i in range(cap))
    return simplified


def min_area_px(depth_m: float, config: MovingConfig) -> float:
    """Depth-scaled minimum component area in pixels."""
    if depth_m <= 0:
        return config.min_area_ref_px
    scaled = config.min_area_ref_px * (config.min_area_ref_depth_m / depth_m) ** 2
    return max(10.0, scaled)


def _convex_hull(points: list[tuple[float, float]]) -> Polygon:
    ordered = sorted(set(points))
    if len(ordered) <= 2:
        return tuple(ordered)

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return tuple(lower[:-1] + upper[:-1])


def areas_from_clusters(clusters: tuple[CandidateCluster, ...]) -> tuple[AreaObservation, ...]:
    """Project candidate clusters into image-space area observations."""
    observations: list[AreaObservation] = []
    for cluster in clusters:
        projected = [(point.x, point.y) for point in cluster.points]
        observations.append(
            AreaObservation(
                frame_id=cluster.frame_id,
                polygon=_convex_hull(projected),
                depth_min_m=cluster.depth_min_m,
                depth_max_m=cluster.depth_max_m,
                point_count=len(cluster.points),
            )
        )
    return tuple(observations)


def _centroid(polygon: Polygon) -> tuple[float, float]:
    return (
        sum(point[0] for point in polygon) / len(polygon),
        sum(point[1] for point in polygon) / len(polygon),
    )


class AreaTracker:
    """Associates area observations into tracks (velocity-scaled gates)."""

    def __init__(self, config: MovingConfig) -> None:
        self._config = config
        self._tracks: list[AreaTrack] = []
        self._next_id = 1

    def update(self, observation: AreaObservation) -> AreaTrack:
        """Associate one observation; returns its track."""
        centroid = _centroid(observation.polygon)
        # Gate scales with the polygon's own extent (depth proxy in
        # image space): fast movers barely overlap frame to frame.
        extent = max(
            max(point[0] for point in observation.polygon)
            - min(point[0] for point in observation.polygon),
            max(point[1] for point in observation.polygon)
            - min(point[1] for point in observation.polygon),
            1.0,
        )
        gate = max(25.0, 2.5 * extent)
        best: AreaTrack | None = None
        best_dist = gate
        for track in self._tracks:
            dist = math.hypot(centroid[0] - track.centroid[0], centroid[1] - track.centroid[1])
            if dist <= best_dist:
                best, best_dist = track, dist
        if best is None:
            best = AreaTrack(self._next_id, observation.frame_id, 0, centroid)
            self._next_id += 1
            self._tracks.append(best)
        best.last_frame_id = observation.frame_id
        best.observation_count += 1
        best.centroid = centroid
        return best
