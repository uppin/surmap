"""Stage 2: moving areas - mask, polygon, area tracks (design step 2).

TODO(n3): implemented by pr-3-moving-differencing's Green row.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class AreaTrack:
    """An area associated across frames."""

    track_id: int
    last_frame_id: int
    observation_count: int


def simplify_polygon(polygon: Polygon, epsilon_px: float, config: MovingConfig) -> Polygon:
    """Douglas-Peucker simplification, capped at config.max_polygon_vertices."""
    raise NotImplementedError("TODO(n3): simplify_polygon")


def min_area_px(depth_m: float, config: MovingConfig) -> float:
    """Depth-scaled minimum component area in pixels."""
    raise NotImplementedError("TODO(n3): min_area_px(Z)")


def areas_from_clusters(clusters: tuple[CandidateCluster, ...]) -> tuple[AreaObservation, ...]:
    """Project candidate clusters into image-space area observations."""
    raise NotImplementedError("TODO(n3): areas_from_clusters")


class AreaTracker:
    """Associates area observations into tracks (velocity-scaled gates)."""

    def __init__(self, config: MovingConfig) -> None:
        self._config = config

    def update(self, observation: AreaObservation) -> AreaTrack:
        """Associate one observation; returns its track."""
        raise NotImplementedError("TODO(n3): AreaTracker.update")
