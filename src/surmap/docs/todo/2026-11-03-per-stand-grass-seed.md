# 2026-11-03 — Each grass stand scattered by its own seed

**Category:** Future enhancement
**Source:** PR #100, stack `#sim-disaster-2` n3
**Packages:** examples/bevy-sitl-poc
**Consent:** n/a — future enhancement (a known limitation of the shipped grass)
**Priority:** 3
**Status:** Open

## What is left

A `vegetation` element's `seed` lays out pines per stand (`vegetation.rs` `plant_pines`), but
grass stands do not get their own: Feronia 0.8.4 has one global `WorldSeed` resource, and
`vegetation/grass.rs` `sow_grass` sets it to the stand's seed before Feronia's scatter pass. When
several grass stands are sown before that pass runs, every one of them is scattered with the
**last-sown** seed. Wanted: each stand scattered with its own seed, still deterministic.

## Why it could not be done now

Feronia scatters every root in one global Setup → Collecting pass, reading the one `WorldSeed`.
Routes: scatter stands one at a time (sow, wait for `ScatterState::Ready`, then the next),
which serialises loading; or offset positions per stand after the scatter; or an upstream
per-root seed in Feronia. Each one changes how the scatter is driven, and the shipped presets have
one grass stand, so nothing in this PR shows the problem.

## What was done instead

`sow_grass` inserts `WorldSeed(stand.seed)`. With one grass stand (the `wildfire-edge` preset)
the layout follows that stand's seed. With several, all follow the last one, deterministically.

## When it becomes possible

Now, with the sequential scatter; or when Feronia takes a seed per `ScatterRoot`.
