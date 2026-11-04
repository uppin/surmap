# 2026-11-04 — Pre-warm smoke emitters in screenshot mode

**Category:** Future enhancement
**Source:** PR #104, stack `#sim-disaster-2` n5 (3 of 4), Wrap row — the planner's D1/D2 screenshot review
**Packages:** examples/bevy-sitl-poc
**Consent:** n/a — future enhancement (D2 passed with the stills as they are)
**Status:** Open
**Plan:** follow-up PR off `main` after `#sim-disaster-2` lands, re-taking the wildfire and building stills together (decided at the #104 wrap)

## What is left

In screenshot mode (`--screenshot <dir> --at <t>`) the simulation clock is pinned at `t`, but
the GPU particles (`bevy_hanabi`) run in real time from when the scene built. A still at t = 900
shows a plume only as old as the seconds the scene took to settle, not 900 s of smoke, so the
plume is shorter and younger than the scene time says. Wanted: emitters pre-warmed in screenshot
mode — run each effect's simulation for its longest lifetime (from its `.fx.json`) before the
still is taken, or spawn with a pre-advanced age — for the building smoke, window flames and the
wildfire's smoke alike.

## Why it could not be done now

It is a change to the screenshot path shared with the wildfire stills (`shots.rs`, `fxdef.rs`)
that n3's and n4's reviewed checkpoints also depend on; doing it at wrap time would change stills
already reviewed in two other PRs.

## What was done instead

The settle wait before a still lets a plume form; D2 at t = 400 and 900 shows a continuous black
plume bending downwind, which passed review.

## When it becomes possible

Now; best after the stack lands (`#sim-disaster-2`), so one change re-takes the wildfire and
building stills together.
