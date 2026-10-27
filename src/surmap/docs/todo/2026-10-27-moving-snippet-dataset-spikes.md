# 2026-10-27 — Monocular snippet dataset spikes and acceptance picks

**Category:** Deferred scope
**Source:** `docs/surmap/1-WIP/2026-10-27-moving-snippets.md` (PR #19, stack `#moving-objects` node 2/6)
**Packages:** surmap
**Consent:** The developer directed the stack's evaluation effort onto the KITTI stereo E2E ("we should put the effort on KITTI stereo e2e", 2026-10-27) after the implementation review recorded these spikes as non-blocking for merge and blocking only for on-board enablement.
**Status:** Open

## What is left

Download and pin the three monocular snippet datasets the design's
§6.1 controls need, and pick the concrete sequences:

- Boreal forest-fire fetch verified against Fairdata (fallback:
  Wennington CC BY 3.0 footage) for the oscillating/fire control.
- VisDrone-MOT sequence pick for the drone-over-street-traffic
  control (official distribution is Drive/Baidu-only; a lawful
  mirror or alternate source must be chosen).
- Purdue swarm window pick (`Clip_50`/`Clip_28` are the densest
  candidates) for the swarm-envelope control.
- Byrne camera-motion check and the COLMAP fx cross-check run.

Each lands as a pinned fetch (URL + size + SHA-256 manifest) in
`scripts/fetch_moving_snippets.py` plus its snippet-acceptance E2E.

## Why it could not be done now

The KITTI stereo snippet — the only control that exercises stages
1–7 together — was judged the highest-value evaluation because it
can invalidate the design rather than merely tune constants. The
developer directed the available effort there; the KITTI fetch,
zip64/span extraction and the stereo E2E landed in PRs #25/#23.
The monocular datasets remain unverified downloads (one is
Drive/Baidu-only), so no honest pin exists yet.

## What was done instead

The snippet registry, oracle converters and `CandidateCluster`
seam are implemented and hermetically tested; the KITTI entry is
fully wired and live-verified. No placeholder manifest or
unverified URL was committed.

## When it becomes possible

Any time — the blockers are dataset-hosting choices, not code.
This item gates snippet acceptance E2Es (n3/n4 deferred rows) and
therefore on-board enablement, not the stack's merge.
