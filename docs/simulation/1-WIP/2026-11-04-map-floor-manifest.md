# Changeset: Simulation map floor — manifest contract

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — cross-language manifest parity, a network port, and a renderer surface

## Summary

The scenario manifest gains an optional `map_floor {sw, ne, texture, zoom}`: a GPS bounding
box and the stitched texture that floors the scene. Both validators — the station's
`validate_manifest` and the renderer's `SceneManifest::from_json` — apply the same rules,
proven on one shared golden fixture (`tests/fixtures/sim_scenario/map-floor.json`, read by
both test suites). Setting a floor replaces the preset ground: the `ground` box element is
removed (its opaque top at 0 m would hide the floor plane), and `clear_map_floor` restores it.

## Stack Context

**Stack**: simulation map floor · slug **`#map-floor`** — this PR is **1 of 5**
**Branch**: `pr-1-map-floor-manifest` · **Base**: `origin/main`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature`

### Green wave

**Wave:** 1 of 3 · **Node:** n2 · **Blocks:** n3 (tool), n4 (renderer)

### Greenable independently?

**yes** — the contract and its validators need nothing above it.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| Tile stitching / `TileSource` | #128 | not present | records only the texture path; never fetches |
| Bevy floor spawn + collider | #130 | not present | defines the manifest it will read |

## Verification

V1 executed: Python tests (size parity with the renderer, ground replacement, clear
restores ground, golden fixture validates) and Rust tests (same fixture parses, size and
texture rules) — both green. Result recorded in the PR body.

## Prerequisites

Step 2b: `2026-11-04-texture-uv-scale-measured.md` — unrelated (floor texture is untiled);
`2026-11-04-cmu-and-pvc-textures.md` — unrelated; `2026-11-03-bevy-visual-checkpoints-v3-v5.md`
— ℹ answered (native-still precedent); `oversized-file-demo-server.md` — unrelated.
**Outcome:** none blocking, no restructure prerequisite.

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, discovery, PRD (stack-level, in #131) · this file
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — failing tests · red commit `3a8de35`
- [wf 3] ✅ 2026-11-04 `/green` Green — size parity, ground replacement, golden fixture · green commit
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
