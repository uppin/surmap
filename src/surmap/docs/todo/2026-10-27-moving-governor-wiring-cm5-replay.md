# 2026-10-27 — Wire BudgetGovernor into the handler and run the CM5-profile replay

**Category:** Deferred scope
**Source:** `docs/surmap/1-WIP/2026-10-27-moving-governance.md` (PR #24, stack `#moving-objects` node 6/6)
**Packages:** surmap
**Consent:** Recorded in the n6 changeset at green; the developer directed effort to the KITTI stereo E2E ("we should put the effort on KITTI stereo e2e", 2026-10-27), which landed green in PR #23.
**Status:** Open

## What is left

Two coupled pieces:

1. Call `BudgetGovernor` from `stream_moving_areas`
   (`surmap.survey.moving_stream`): feed it the stage counters
   (layer voxels, candidate points, areas, keypoints, buffer
   bytes) per analyzed frame and apply its degradation ladder
   (drop keypoints → drop areas → widen stride) when a cap is
   hit. Today the governor is implemented and unit-tested but
   never invoked by the running stream, so the design §2 caps
   are unenforced on-board.
2. The CM5-profile replay: EuRoC + KITTI through the sidecar
   at CM5-class CPU limits, recording the §2 budget table
   (per-stage ms/frame, layer memory against the 2 M-voxel cap,
   ladder engagements) into the design's §5 record.

## Why it could not be done now

The handler assembly the governor must govern only became
final at n5 of this stack, and the remaining evaluation effort
went to the KITTI chain by the developer's direction. A replay
run before the wiring exists would measure a pipeline that is
not the one that ships.

## What was done instead

`BudgetGovernor`, `StageCounters` and the degradation ladder
are implemented behind the stage APIs with unit tests pinning
cap arithmetic and ladder order; nothing on-board runs with
the moving stream enabled by default, so the unenforced caps
are not yet a field risk.

## When it becomes possible

Any time after PR #23 lands. This item is the gate for
enabling the moving-object stream on-board by default.
