# 2026-11-04 — Measure `uv_scale` for timber, roof_tiles and slate

**Category:** Future enhancement
**Source:** PR #105, stack `#sim-disaster-2` n6 (4 of 4), Wrap row
**Packages:** examples/bevy-sitl-poc
**Consent:** n/a — polish beyond the approved review (the planner approved the D1 district stills)
**Priority:** 5
**Status:** Open
**Plan:** ⚠️ recorded debt — no PR planned (decided at the #105 wrap)

## What is left

`uv_scale` of the `timber` facade and the `roof_tiles` and `slate` roofs was set by counting
boards, tiles and slates in the texture against their real size, not from the source's metadata.
Wanted: each set's real-world size from its Poly Haven / ambientCG metadata (the `dimensions` of
the asset), and `uv_scale` = 1 / that size, so a tile, a slate and a board are their real size.

## Why it could not be done now

The sweep's texture item was judged by stills; the counted scales read correctly at survey range,
and the metadata lookup was not part of the review.

## What was done instead

Scales estimated by counting features; the D1 stills (old-town, suburban) passed review with them.

## When it becomes possible

Now: read each set's dimensions, set `uv_scale` in `building/facades/timber.facade.json` and
`building/roofs/{roof_tiles,slate}.roof.json`, and re-shoot D1.
