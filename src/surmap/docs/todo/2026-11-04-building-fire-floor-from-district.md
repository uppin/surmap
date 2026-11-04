# 2026-11-04 — Check a building fire's floor when the floor count comes from the district

**Category:** Future enhancement
**Source:** PR #104, stack `#sim-disaster-2` n5 (3 of 4), Wrap row
**Packages:** surmap, examples/bevy-sitl-poc
**Consent:** n/a — future enhancement (the station refuses every floor it can count; the renderer refuses the rest loudly)
**Status:** Open
**Plan:** follow-up in the stack's sweep node, stacked on #104 (decided at the #104 wrap)

## What is left

`surmap.simulation.building_presets.validate_buildings` (and so `add_building_fire`) checks
`0 ≤ floor < floors` only when the building names its own `floors`. When the count comes from
its district — `floor(height / floor_m)` with the district preset's `floor_m` — the station
accepts any floor, and the renderer then fails the scene at load (`building.rs` `build_fires`:
*floor N is not below B's M floors*). Wanted: the station resolves floors the renderer's way —
read the district preset file (shipped name or path, under `ScenarioStore.assets_dir`), take the
last district holding the building's centre, and refuse the fire with the same message.

## Why it could not be done now

The station's manifest rules are pure and file-free today; reading district presets means passing
the assets directory into `validate_manifest` and every edit that calls it, a signature change
across `scenario_manifest` and the tools that grows a reviewed diff at wrap time.

## What was done instead

The station refuses a floor beyond an explicit `floors`; the renderer refuses the rest by name, so
a bad scene never draws silently. `downtown-blaze` gives its tower `floors: 12`.

## When it becomes possible

Now: thread `assets_dir` (already on `ScenarioStore`) into the building validation.
