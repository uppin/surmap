# Changeset: Simulation map floor — agent tools

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — cross-language manifest parity, a network port, and a renderer surface

## Summary

The agent's hands on the floor: `set_map_floor` (stitch → store texture → anchor scenario;
the scenario is resolved before anything is written, so a bad id leaves no orphan),
`clear_map_floor`, and `geo_to_enu` / `enu_to_geo` so the agent places objects by GPS
through a tool instead of doing cos(lat) maths itself. `set_map_floor` warns when
re-anchoring keeps placed elements' ENU positions or leaves an element outside the new
floor. © OpenStreetMap contributors enters the scenario's credits whenever a floor is set.

## Stack Context

**Stack**: `#map-floor` — **3 of 5** · **Branch**: `pr-3-map-floor-tool` · **Base**: `pr-2-map-floor-tiles`
**Kind**: Feature · behaviour-adds · **Workflow**: preset `feature`

### Green wave

**Wave:** 2 of 3 · **Node:** n3 · **Blocks:** n5 (the agent e2e drives these tools)

### Greenable independently?

**no — needs #127 + #128 green**: the handler test drives the real manifest contract and
the real stitch port (through the in-memory adapter).

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `set_map_floor` / `clear_map_floor` manifest edits | #127 | implemented below | calls them; does not reimplement |
| `stitch_floor`, `GeoBBox`, geodesy | #128 | implemented below | calls them through `TileSource` |

## Verification

V1 executed: handler tests over fake tiles + a real store (floor set, geo conversion both
ways, clear restores ground, texture on disk, warnings/credits asserted at the store).
Green at this branch's tip.

## Prerequisites

As #127. **Outcome:** none blocking.

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset and discovery · this file
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — failing tool tests · red commit `9defd35`
- [wf 3] ✅ 2026-11-04 `/green` Green — geo tools, clear, credits, warnings · green commit
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
