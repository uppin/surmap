# 2026-11-04 — Let legacy, material-only buildings burn

**Category:** Future enhancement
**Source:** PR #104, stack `#sim-disaster-2` n5 (3 of 4), Wrap row
**Packages:** examples/bevy-sitl-poc, surmap
**Consent:** n/a — future enhancement (the PRD keeps legacy buildings rendering as before; burning them was not planned)
**Status:** Open
**Plan:** ⚠️ recorded debt — no PR planned until a scenario needs a legacy building to burn (decided at the #104 wrap)

## What is left

Only preset-styled buildings burn: `building.rs` `build_fires` builds footprints from the styled
buildings only, so a `building_fires` entry naming a building outside every district with only a
`material` (the shipped `earthquake-block` buildings, for example) fails the scene at load
(*is not drawn from presets*). The station's `validate_buildings` does not refuse it yet, so the
agent learns only from the renderer. Wanted, either: legacy buildings get a footprint and a floor
count (`DEFAULT_FLOOR_M`) and burn with a generic charred band and the window grid's panes; or,
at least, the station refuses such a fire with the renderer's message.

## Why it could not be done now

A legacy building is one cuboid with one material and a pane grid, with no per-floor meshes for
the fire to change, and a burnt look for it is a visual decision nobody specified.

## What was done instead

Legacy buildings render exactly as before; every district or preset building can burn; the
renderer refuses a fire it cannot draw by name.

## When it becomes possible

Now: decide burn-or-refuse, then either the per-floor legacy meshes with a planner-reviewed still,
or a station rule mirroring the renderer's.

**Consent:** deferred by the developer at the `sim-disaster-2` TODO gate (2026-11-04): not carried by the sweep node; stays recorded debt.
