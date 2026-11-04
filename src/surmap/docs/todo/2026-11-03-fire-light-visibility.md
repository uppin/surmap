# 2026-11-03 — Show that the fire's point light adds visible light

**Category:** Future enhancement
**Source:** PR #100, stack `#sim-disaster-2` n3 — planner's V4 screenshot review
**Packages:** examples/bevy-sitl-poc
**Consent:** n/a — follow-up verification. The planner could not tell the light apart from the
glowing rim in the W2 stills.
**Priority:** 3
**Status:** Open

## What is left

An A/B still: `wildfire-edge` at t = 40 s and 120 s with the `light` block of
`fx/flames.fx.json` and without it (same seed, same camera: `--screenshot <dir> --at <t>
--scenario wildfire-edge`), compared on the pines and ground near the front. If the difference is
invisible, retune `lumens_per_m` / `range_m` in JSON, or drop the light.

## Why it could not be done now

The light ships with the spec's values and is spawned per fire (`wildfire.rs` `refresh_fire`),
but in the review stills the rim's emissive glow and bloom dominate the same pixels; the A/B pair
was not in the review plan.

## What was done instead

One unshadowed point light per fire at the perimeter centroid, 2 m up, colour
`[1.0, 0.55, 0.2]`, intensity `lumens_per_m` × perimeter length, `range_m` 60 — all from
`fx/flames.fx.json`.

## When it becomes possible

Now.
