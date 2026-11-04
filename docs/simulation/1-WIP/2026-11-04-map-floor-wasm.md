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

V1 executed: cargo tests for the collider half-extents, preset-ground hiding, and the
shared golden fixture — 365 Rust tests green. **Not done: the native screenshot** (needs
the 66 MB asset fetch + release build); texture orientation follows Bevy's UV convention
and remains the one manual check, recorded here honestly rather than claimed.

## Prerequisites

As #127. **Outcome:** none blocking.

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset and discovery · this file
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — failing Rust tests · red commit `694d86b`
- [wf 3] ✅ 2026-11-04 `/green` Green — floor collider + ground hiding · green commit `2dbe821`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (screenshot outstanding, see Verification)
