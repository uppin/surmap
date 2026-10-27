# 2026-10-27 — Runtime VO increments for correction distribution

**Category:** Deferred scope
**Source:** `docs/surmap/1-WIP/2026-10-27-moving-placement.md` (PR #23, stack `#moving-objects` node 5/6)
**Packages:** surmap
**Consent:** Recorded as design open question 1's consequence; the developer directed effort to the KITTI stereo E2E ("we should put the effort on KITTI stereo e2e", 2026-10-27), which landed green without runtime VO.
**Status:** Open

## What is left

Feed real visual-odometry increments into the observation
buffer: `stream_moving_areas` currently stores
`vo_translation = 0` for every observation, so
`distribute_correction` falls back to time-fraction
interpolation between bracketing keyframe poses (~25 cm error
class at 1 s keyframe spacing under acceleration — the error
the design's step 6 pose-graph-lite distribution exists to
avoid). A frame-to-frame VO source (design OQ1) must supply
per-observation increments, and the same source should feed
τ's θ̂ pose-drift term, which currently also defaults to 0.

## Why it could not be done now

There is no runtime VO on the CM5 path yet: poses exist only
at RTAB flush. Building VO is its own component decision
(OQ1), out of this stack's scope.

## What was done instead

Placement degrades to bracketing-keyframe distribution with
the correction still applied in VO-increment *form* (the
buffer schema carries `vo_translation`; only its source is
missing). The KITTI E2E (PR #23) measured the resulting
placement at 1.32 m from a labelled car — within the 4 m
acceptance for this chain, with the interpolation error
visible in that margin.

## When it becomes possible

When a runtime VO source is chosen under design OQ1. Gates
tighter placement accuracy claims and on-board enablement at
survey speed, not this stack's merge.
