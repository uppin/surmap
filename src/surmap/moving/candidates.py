"""The stage-1 → stage-2 seam: dynamic candidate clusters.

Stage 1 (stereo differencing, n3) produces these; stage 2
(moving areas) consumes them. Snippet oracles (n2) synthesize
the same type in tests, so stages 2-5 run production code
against recorded data.
"""

from __future__ import annotations

from dataclasses import dataclass

from surmap.types import Vec3


@dataclass(frozen=True)
class CandidateCluster:
    """Points that differenced away from the static layer, on one frame."""

    frame_id: int
    t_ns: int
    points: tuple[Vec3, ...]
    depth_min_m: float
    depth_max_m: float

    def __post_init__(self) -> None:
        if self.depth_max_m < self.depth_min_m:
            raise ValueError("depth_max_m must be >= depth_min_m")
        if not self.points:
            raise ValueError("a candidate cluster needs at least one point")
