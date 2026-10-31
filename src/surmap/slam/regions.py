"""Region-of-interest port: a polygon on one frame's image in, dense map-frame points out.

A requester (the station with its SAM masks, or the demo) names a frame,
the channel the polygon was drawn on, the size of that image, and the
polygon. The answer is every point stereo recovers inside the polygon on
that one frame — never accumulated across frames or queries — placed in
the map frame. Points are a read-only layer on RTAB-Map's output, never
written back into its map (docs/architecture.md section 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from surmap.types import Vec3


class RegionStatus(Enum):
    """How a region query was answered; the value is the sidecar's wire name."""

    OK = "ok"
    FRAME_EXPIRED = "expired"
    NO_POSE = "no_pose"
    INVALID_QUERY = "invalid"


@dataclass(frozen=True)
class RegionQuery:
    """One region of interest: polygon in `(width, height)` image pixels of `channel`."""

    query_id: int
    frame_id: int
    channel: int
    width: int
    height: int
    polygon: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class RegionResult:
    """The answer to one query; `points` are map-frame and empty unless `OK`."""

    query_id: int
    frame_id: int
    channel: int
    status: RegionStatus
    points: tuple[Vec3, ...] = ()


def invalid_reason(query: RegionQuery) -> str | None:
    """Why `query` cannot be answered, or None when it is well formed."""
    if query.channel not in (0, 1):
        return "channel must be 0 or 1"
    if len(query.polygon) < 3:
        return "polygon needs at least 3 vertices"
    if query.width <= 0 or query.height <= 0:
        return "image size must be positive"
    return None


@runtime_checkable
class RegionPointSource(Protocol):
    def region_points(self, query: RegionQuery, timeout: float = 5.0) -> RegionResult: ...


@dataclass
class InMemoryRegionPointSource:
    """`RegionPointSource` for tests and simulation: configured points per frame.

    A frame it does not hold answers `FRAME_EXPIRED`, as a real ring
    would once the frame has aged out. Every query is recorded.
    """

    points_by_frame: dict[int, tuple[Vec3, ...]]
    queries: list[RegionQuery] = field(default_factory=list)

    def region_points(self, query: RegionQuery, timeout: float = 5.0) -> RegionResult:
        self.queries.append(query)
        points = self.points_by_frame.get(query.frame_id)
        if points is None:
            return RegionResult(
                query.query_id, query.frame_id, query.channel, RegionStatus.FRAME_EXPIRED
            )
        return RegionResult(query.query_id, query.frame_id, query.channel, RegionStatus.OK, points)
