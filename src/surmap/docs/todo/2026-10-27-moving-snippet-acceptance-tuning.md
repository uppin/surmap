# 2026-10-27 — Snippet acceptance runs and verdict-threshold tuning

**Category:** Deferred scope
**Source:** `docs/surmap/1-WIP/2026-10-27-moving-classification.md` (PR #22, stack `#moving-objects` node 4/6)
**Packages:** surmap
**Consent:** The developer directed the stack's evaluation effort onto the KITTI stereo E2E ("we should put the effort on KITTI stereo e2e", 2026-10-27) after the implementation review recorded threshold tuning as non-blocking for merge and blocking for on-board enablement.
**Status:** Open

## What is left

Run the three monocular snippet acceptance controls (traffic
graduation/identity, fire zero-graduation, swarm envelope) and
tune the verdict constants on a split-half of the snippets:
net/path thresholds (0.6 rigid / 0.25 oscillating), velocity
coherence (0.6 / 0.35), and `tau_depth_k`. Record the deciding
statistics per snippet in the design's §6 evaluation record.

## Why it could not be done now

Blocked on the dataset spikes recorded in
`src/surmap/docs/todo/2026-10-27-moving-snippet-dataset-spikes.md`
— the monocular datasets are not yet pinned (one is
Drive/Baidu-only), so there is nothing byte-identical to tune
against. Tuning on synthetic data instead would fit constants
to the test fixtures, not to real footage.

## What was done instead

Thresholds ship as documented design starting points in
`surmap.moving.config.MovingConfig`; the verdict machine's
mechanics (terminal verdicts, versioning, decelerating-car
no-flap) are unit-tested, and the KITTI positive control (PR
#23) shows the shipped constants graduate real traffic.

## When it becomes possible

When the dataset-spikes record closes. This item gates
on-board enablement of the moving-object stream (untuned
thresholds must not fly), not the stack's merge.
