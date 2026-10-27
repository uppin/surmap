# 2026-10-27 — EuRoC negative-control replay through the moving stream

**Category:** Deferred scope
**Source:** `docs/surmap/1-WIP/2026-10-27-moving-differencing.md` (PR #21, stack `#moving-objects` node 3/6)
**Packages:** surmap
**Consent:** The developer directed the stack's evaluation effort onto the KITTI stereo E2E ("we should put the effort on KITTI stereo e2e", 2026-10-27); the KITTI chain landed green in PR #23.
**Status:** Open

## What is left

Replay a static EuRoC segment through the assembled
`StreamMovingAreas` handler (real `SidecarRtabmapBackend` poses,
real stereo) and assert the design §6 false-graduation metric:
zero RIGID_MOVER verdicts and zero graduated snapshots on a
scene with no movers, with the candidate/area counts reported.

## Why it could not be done now

The handler only became fully assembled (verdicts, keypoints,
flush snapshots) at n5 of this stack, and the developer directed
the remaining evaluation effort to the KITTI stereo E2E — the
positive control that can invalidate the design. The negative
control needs the same assembled handler plus a static-scene
replay harness that does not exist yet.

## What was done instead

The positive control landed: `tests/test_moving_kitti_e2e.py`
(PR #23) runs the full chain on KITTI and asserts graduation and
placement against ground-truth labels. Unit tests pin the
false-positive mechanics that exist at this tier (dwell
absorption, ghost decay, cluster persistence).

## When it becomes possible

Any time after PR #23 lands — the assembled handler and the
KITTI E2E's staging pattern are the prerequisites, and both
exist. This item gates on-board enablement (a false-graduation
rate is a §6 acceptance metric), not the stack's merge.
