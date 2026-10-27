"""Red tests for n6: resource governance."""

from __future__ import annotations

from surmap.moving.config import MovingConfig
from surmap.moving.governance import BudgetGovernor, Degradation, StageCounters

CONFIG = MovingConfig()
UNDER = StageCounters(
    points_sampled=4000,
    areas_live=3,
    buffered_observations=40,
    layer_voxels=100_000,
    ms_stage_total=80.0,
)
OVER_AREAS = StageCounters(
    points_sampled=4000,
    areas_live=500,
    buffered_observations=40,
    layer_voxels=100_000,
    ms_stage_total=80.0,
)
OVER_LAYER = StageCounters(
    points_sampled=4000,
    areas_live=3,
    buffered_observations=40,
    layer_voxels=CONFIG.max_voxels + 1,
    ms_stage_total=80.0,
)


def test_under_budget_runs_full() -> None:
    assert BudgetGovernor(CONFIG).evaluate(UNDER) is Degradation.FULL


def test_area_flood_degrades_and_caps() -> None:
    governor = BudgetGovernor(CONFIG)
    assert governor.evaluate(OVER_AREAS) is not Degradation.FULL
    assert governor.cap_areas(500) == CONFIG.max_areas


def test_layer_over_cap_is_never_full() -> None:
    assert BudgetGovernor(CONFIG).evaluate(OVER_LAYER) is not Degradation.FULL
