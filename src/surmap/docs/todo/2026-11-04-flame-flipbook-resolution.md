# 2026-11-04 — A higher-resolution flame flipbook

**Category:** Future enhancement
**Source:** PR #105, stack `#sim-disaster-2` n6 (4 of 4), Wrap row
**Packages:** examples/bevy-sitl-poc
**Consent:** n/a — polish beyond the approved review (the planner approved the flipbook flames in review round 1)
**Priority:** 4
**Status:** Open
**Plan:** ⚠️ recorded debt — no PR planned; a JSON and `assets.lock.json` change once a sheet is found (decided at the #105 wrap)

## What is left

`flames` and `window_flames` animate through `textures/fx/flame_tongues.png`, OpenGameArt
"Animated Fire" `fire1_64.png` (CC0, 10 × 6 frames of 64 px). At survey range the tongues read;
in the close still (`flame-close.png`, 8 m from the front) a 64 px frame stretched over a 1–2.6 m
particle reads as wispy rather than as a crisp tongue. Wanted: a CC0 flame sprite sheet with frames
of 128 px or more, pinned in `assets.lock.json` and named by the two effects' `flipbook`.

## Why it could not be done now

No CC0 sheet at 128 px or more was found during the sweep; the 64 px sheet was the best CC0 source
and passed the planner's review.

## What was done instead

The 64 px flipbook ships, with the flame gradients scaled × 0.4 so the tongues resolve instead of
washing out, and `stretch` 1.0 so the sprite stays upright.

## When it becomes possible

Now: find the sheet (OpenGameArt, Kenney, ambientCG), swap the `flipbook` texture, columns, rows and
fps, re-shoot `flame-close.png` and the W2 fire-eye still.
