# 2026-11-04 — No on-board detector finds the simulation's train

**Category:** Future enhancement
**Source:** PR #106, stack `sim-traffic` n1 (1 of 3), Green row `[wf 3]` — the detector cross-check
**Packages:** examples/bevy-sitl-poc, src/surmap
**Consent:** the developer's requirement of 2026-11-04 ("improve realism where the detectors miss"), with the orchestrator's rule that a class still under the bar after three iterations is recorded, not faked
**Priority:** 4
**Status:** Open
**Plan:** ⚠️ recorded debt — no PR planned

## What is left

`street-traffic`'s train is found by none of the three Coral COCO profiles: 0/6 object-frames in
view (score 0.3, one lap of the survey loop; the bar is ≥ 20 % for the best profile). Car, bus and
truck clear it (`docs/simulation/bevy-simulation.md` § *Road and rail vehicles*).

## Why it could not be done now

Three iterations were spent: the rail 36 m closer to the loop (the locomotive is then clipped by
the top of the image, and ssdlite calls the tender's figure a person), the rail 22 m closer with
a slower train (the same six frames), and a tint (it cannot lighten a glTF whose colours are
linear 0.02–0.04). What is left needs a different locomotive model or a per-material colour
override, and a model is a new asset decision (CC0 preferred; CC BY only with an `attribution`),
not a tweak.

## What was done instead

The train stays as pinned (Quaternius locomotive and wagon, CC0) on the rail 48 m west of the
loop; the score table records 0/6 on every profile so the gap is visible.

## When it becomes possible

Pick a lighter, more modern locomotive (Kenney's train kit, or another CC0 pack) or add a class
field that recolours named materials; re-record `street-traffic` as in *Road and rail vehicles*
and aim for a locomotive 100–250 px wide and fully inside the frame for several frames. The train
is in view only while the loop passes it, so a window where the camera looks along the rail helps.
