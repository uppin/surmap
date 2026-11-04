# 2026-11-04 — The on-board detectors miss the simulation's boats and never see its ship

**Category:** Future enhancement
**Source:** PR #109, stack `sim-traffic` n3 (3 of 3), Green row `[wf 3]` — the detector cross-check
**Packages:** examples/bevy-sitl-poc, src/surmap
**Consent:** the developer's requirement of 2026-11-04 ("improve realism where the detectors miss"), with the developer's instruction of the same day to fast-track the wrap and move non-essential work to TODOs
**Priority:** 4
**Status:** Open
**Plan:** ⚠️ recorded debt — no PR planned

## What is left

On `flood-rescue`, the best profile (ssdlite-mobiledet) finds a boat in 3 of 47 object-frames it
is in view (6 %). The other two profiles find none. The bar is ≥ 20 % for the best profile. The
ship, scored on an untracked variant with 40 m of water and one moored ship, is in view in 0
frames. Numbers: `docs/simulation/bevy-simulation.md` § *Boats and ships (`flood-rescue`)*.

## Why it was not done now

The developer asked for the wrap to be fast-tracked, so the three realism iterations the other
classes got were not run for vessels.

## Leads

- **Check the scoring first.** ssdlite fires `boat` 66 times on the preset but matches only 3.
  Compare its detection boxes with the expected ones (frames 20–60). The expected box may sit at
  the wrong height: the track's `enu.z` is the water top (0.6 m), and heave and `keel_below_origin_m`
  are not in it. If so, fix `detection_eval`'s vessel box before touching the scene.
- **The ship's in-view rule.** Its box includes 44.9 m masts, so from the survey loop's altitude
  it is never half inside the frame. Either score a ship by its hull height, not the masts, or
  pick a CC0 motor ship (a ferry or freighter) instead of the three-masted sailing ship.
- **Boat realism.** Try a white or orange hull tint (rescue boats), a larger rescue-boat class
  (6–8 m), and a wake on the water surface for contrast. Re-record and re-score after each.
