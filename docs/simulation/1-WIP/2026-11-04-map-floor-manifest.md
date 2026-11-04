# Changeset: Simulation map floor — map-floor-manifest

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — cross-language manifest parity, a network port, and a renderer surface

## Summary

Manifest contract: optional `map_floor {sw, ne, texture, zoom}` validated identically by Python and Rust; ENU centre/size derived from the bbox.

## Initial Discovery

[2026-11-04-map-floor-manifest-initial-discovery.md](2026-11-04-map-floor-manifest-initial-discovery.md)

## Stack Context

**Stack**: simulation map floor · slug **`#map-floor`** — this PR is **1/5**
**Branch**: `pr-1-map-floor-manifest` · **Base**: predecessor in the `#map-floor` stack (or `origin/main` for the bottom PR)
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = failing tests

### Green wave

**Wave:** 1 of 3
**Node:** n2
**Blocks:** the nodes above it in the `#map-floor` line

### Greenable independently?

**yes**

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| (see Summary) | none — bottom contract | stub / fixture | calls it; does not implement it |

## Verification

**Method:** V1 — Python/Rust parity tests on inline manifests
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
