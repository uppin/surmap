# Changeset: Simulation map floor — Bevy rendering

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — cross-language manifest parity, a network port, and a renderer surface

## Summary

The renderer draws the floor: one untiled plane at the ENU origin, sized from the bbox,
textured with the stitched PNG (which receives the mip chain every asset-server image
gets, so it does not shimmer from altitude). Because the ground box is gone, the floor
carries a fixed collider whose top is at 0 m — what people, vehicles and nests stand on.
A hand-edited manifest that still carries the preset `ground` box has it hidden by the
renderer as a second line of defence.

## Stack Context

**Stack**: `#map-floor` — **4 of 5** · **Branch**: `pr-4-map-floor-wasm` · **Base**: `pr-3-map-floor-tool`
**Kind**: Feature · behaviour-adds · **Workflow**: preset `feature`

### Green wave

**Wave:** 2 of 3 · **Node:** n4 · **Blocks:** n5 (served-scene confidence)

### Greenable independently?

**yes** — against the manifest contract and a fixture texture from #127.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `map_floor` parsing/validation | #127 | implemented below | reads `centre_and_size_enu`; does not re-validate beyond it |

## Verification

V1 executed: cargo tests for the collider's world-space bounds (a slab spanning the
floor, top at 0 m — the earlier rotated-cuboid wall is fixed and its bug-encoding test
replaced), preset-ground hiding, and the shared golden fixture — 365 Rust tests green.
Native screenshot executed 2026-11-04 (release build, `--scenario map-floor-shot --at 8`,
real OSM tiles over Vilnius 54.680–54.684 / 25.270–25.282 at zoom 18): `overview.png`
shows the map floor readable and correctly oriented (street names legible, not mirrored),
the placed building on it, and the survivor standing on the floor at its corner; `chase.png`
shows "© OpenStreetMap contributors" in-frame and the drone over the floor. No wall or
flicker artifact. The collider's effect is the standing figure plus the world-bounds test.

## Prerequisites

As #127. **Outcome:** none blocking.

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset and discovery · this file
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — failing Rust tests · red commit `694d86b`
- [wf 3] ✅ 2026-11-04 `/green` Green — floor collider + ground hiding · green commit `2dbe821`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [x] Verification executed — result recorded (cargo tests + native screenshot, see Verification)
