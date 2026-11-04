# Changeset: Simulation map floor — map-floor-tool

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — cross-language manifest parity, a network port, and a renderer surface

## Summary

`set_map_floor` SimulationTools rpc: stitches, stores the texture in the library, anchors the scenario; response carries centre/size/zoom.

## Initial Discovery

[2026-11-04-map-floor-tool-initial-discovery.md](2026-11-04-map-floor-tool-initial-discovery.md)

## Stack Context

**Stack**: simulation map floor · slug **`#map-floor`** — this PR is **3/5**
**Branch**: `pr-3-map-floor-tool` · **Base**: predecessor in the `#map-floor` stack (or `origin/main` for the bottom PR)
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = failing tests

### Green wave

**Wave:** 2 of 3
**Node:** n3
**Blocks:** the nodes above it in the `#map-floor` line

### Greenable independently?

**no — needs n1+n2 green for its handler test**

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| (see Summary) | n2 manifest shape + n1 stitch port (stubs during planning) | stub / fixture | calls it; does not implement it |

## Verification

**Method:** V1 — handler test over fake tiles + real store
- [ ] Verification executed — result recorded

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — failing tests, committed ·
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes ·
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded

## Prerequisites

Step 2b cross-check (`src/surmap/docs/todo/`, `src/surmap/docs/code-issues/`):

| Record | Verdict |
|---|---|
| `src/surmap/docs/todo/2026-11-04-texture-uv-scale-measured.md` | — unrelated: facade/roof `uv_scale`; the floor texture is untiled |
| `src/surmap/docs/todo/2026-11-04-cmu-and-pvc-textures.md` | — unrelated: facade texture sourcing |
| `src/surmap/docs/todo/2026-11-03-bevy-visual-checkpoints-v3-v5.md` | ℹ answered: native-still inspection is this stack's V1 visual check precedent; V3–V5 themselves stay open |
| `src/surmap/docs/code-issues/oversized-file-demo-server.md` | — unrelated: demo server file size |

**Outcome:** none blocking, no restructure prerequisite.
