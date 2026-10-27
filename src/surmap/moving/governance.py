"""Stage governance: counters, caps, degradation ladder (design section 5)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from surmap.moving.config import MovingConfig

_MAX_BUFFERED = 10_000
_MAX_STAGE_MS = 1_000.0

_LADDER = (
    "FULL",
    "REDUCED_CADENCE",
    "FEWER_KEYPOINTS",
    "DETECTOR_LABELLED_ONLY",
    "OFF",
)


class Degradation(Enum):
    """Degradation ladder steps, in order (feature degrades, never RTAB)."""

    FULL = "full"
    REDUCED_CADENCE = "reduced_cadence"
    FEWER_KEYPOINTS = "fewer_keypoints"
    DETECTOR_LABELLED_ONLY = "detector_labelled_only"
    OFF = "off"


@dataclass(frozen=True)
class StageCounters:
    """Per-stage budget counters for one reporting window."""

    points_sampled: int
    areas_live: int
    buffered_observations: int
    layer_voxels: int
    ms_stage_total: float


class BudgetGovernor:
    """Enforces caps; steps the ladder under sustained over-budget."""

    def __init__(self, config: MovingConfig) -> None:
        self._config = config

    def evaluate(self, counters: StageCounters) -> Degradation:
        """Current degradation level for these counters.

        Each violated budget (area cap, layer-voxel cap, buffer
        cap, stage-time budget) steps the ladder one rung from
        FULL; RTAB-Map is never degraded.
        """
        violations = sum(
            (
                counters.areas_live > self._config.max_areas,
                counters.layer_voxels > self._config.max_voxels,
                counters.buffered_observations > _MAX_BUFFERED,
                counters.ms_stage_total > _MAX_STAGE_MS,
            )
        )
        return Degradation(_LADDER[min(violations, len(_LADDER) - 1)].lower())

    def cap_areas(self, areas_live: int) -> int:
        """How many of `areas_live` areas may be kept (largest win)."""
        return min(areas_live, self._config.max_areas)
