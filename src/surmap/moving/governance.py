"""Stage governance: counters, caps, degradation ladder (design section 5).

TODO(n6): implemented by pr-6-moving-governance's Green row.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from surmap.moving.config import MovingConfig


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
        """Current degradation level for these counters."""
        raise NotImplementedError("TODO(n6): BudgetGovernor.evaluate")

    def cap_areas(self, areas_live: int) -> int:
        """How many of `areas_live` areas may be kept (largest win)."""
        raise NotImplementedError("TODO(n6): BudgetGovernor.cap_areas")
