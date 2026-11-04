# 2026-11-04 — Per-window variation in a burning floor's glow

**Category:** Future enhancement
**Source:** PR #104, stack `#sim-disaster-2` n5 (3 of 4), Wrap row — the planner's D1/D2 screenshot review
**Packages:** examples/bevy-sitl-poc
**Consent:** n/a — future enhancement (the visual spec asks for one glow colour and intensity; D2 passed with it)
**Status:** Open
**Plan:** follow-up PR off `main` after `#sim-disaster-2` lands (a visual round for the planner; decided at the #104 wrap)

## What is left

Every window on a burning floor glows identically: one emissive glow plane per floor
(`building/walls.rs`, drawn by `building/fire_view.rs`) with `building/fire.json`'s
`glow_colour` × `glow_intensity`. Real fires flicker unevenly room by room. Wanted: per-window
variation — a seeded intensity spread and a flicker rate and depth — whose numbers live in
`building/look.json` (`fire` block), never in Rust; seeded from the building id and window
index so stills and recordings stay deterministic.

## Why it could not be done now

The visual spec named a single glow; variation is a new visual decision for the planner, and the
glow is one mesh per floor, so per-window values need per-window meshes or a per-vertex
attribute — a renderer change the D2 review did not cover.

## What was done instead

The glow went from near-white to 3.5 in orange (`[1.0, 0.42, 0.10]`) in the D2 round, and D2
passed with uniform floor bands.

## When it becomes possible

Now: a visual-spec line for the variation, the `look.json` fields, and a D2 still to review.
