"""Incremental point emission for the CM5 survey stream.

Producers (RTAB-Map, object reconstruction) return full per-frame point
sets. This emitter forwards only newly spawned points: a point at a
position already sent for the same designation in this stream is never
resent. Seen state is per stream — create an emitter per stream, and
`reset` it when the stream's terms change (e.g. a new calibration).
"""

from __future__ import annotations

from collections.abc import Iterable

from surmap.types import Vec3


class IncrementalPointEmitter:
    """Forwards spawn-only points, per designation, for one stream."""

    def __init__(self) -> None:
        self._seen: set[tuple[int, float, float, float]] = set()

    def emit(self, designation: int, points: Iterable[Vec3]) -> tuple[Vec3, ...]:
        """The points in `points` not yet sent under `designation`, in order."""
        fresh: list[Vec3] = []
        for point in points:
            key = (designation, point.x, point.y, point.z)
            if key not in self._seen:
                self._seen.add(key)
                fresh.append(point)
        return tuple(fresh)

    def reset(self) -> None:
        """Forget every sent position; the next emission starts fresh."""
        self._seen.clear()
