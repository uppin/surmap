# Moving-area resource budgets and degradation ladder

**Date:** 2026-10-27
**Type:** Infra
**Packages:** surmap

Implemented the design §5 governance for the moving-object
pipeline: per-stage counters (`StageCounters`), hard caps
(2 M static-layer voxels, 32 live areas, observation-buffer cap
evicting least-coherent tracks first) and the four-step
degradation ladder (`BudgetGovernor` in
`surmap.moving.governance`: cadence 5→2 Hz, keypoints 16→8,
stage 4 restricted to detector-labelled areas, feature off with
areas still logged). The static pipeline is never degraded.

Verification: red-first unit tests (3 failed at the red commit)
green at implementation; on the wrapped stack tip
`uv run pytest -q` 473 passed, `uv run mypy` strict clean,
`uv run ruff check`/`format` clean.

Deferred in
`src/surmap/docs/todo/2026-10-27-moving-governor-wiring-cm5-replay.md`:
invoking the governor from the running handler and the
CM5-profile replay that produces the measured §2 budget table.
That record is the gate for enabling the moving stream
on-board by default; it does not gate this node's merge.
