# Changeset: Simulation map floor — agent end-to-end

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — cross-language manifest parity, a network port, and a renderer surface

## Summary

The feature becomes discoverable and proven end to end: the scene-building subagent's
skill teaches the map-floor flow (base first, place by GPS through `geo_to_enu`, heed the
warnings, credit OSM), the stack PRD lives with this node, and a real agent turn on a
real socket — scripted model, real store, fake tiles — bases a scenario on a bbox,
converts a GPS target through the tool, places a building, and the station serves the
manifest and the floor PNG.

## Stack Context

**Stack**: `#map-floor` — **5 of 5** · **Branch**: `pr-5-map-floor-e2e` · **Base**: `pr-4-map-floor-wasm`
**Kind**: Feature · behaviour-adds · **Workflow**: preset `feature`

### Green wave

**Wave:** 3 of 3 · **Node:** n5 · **Blocks:** nothing

### Greenable independently?

**no — needs #129 + #130**: the e2e drives the real tools the agent will call.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| All floor tools and rendering | #127–#130 | implemented below | exercises them; implements none |

## Verification

V1 executed: `tests/test_sim_map_floor_e2e.py` (agent turn, served manifest + PNG, OSM
credit) plus the full Python suite and gates at the stack tip. Screenshot check remains
outstanding in #130, recorded there.

## Prerequisites

As #127. **Outcome:** none blocking.

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, discovery and the stack PRD · this file
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — failing agent e2e · red commit
- [wf 3] ✅ 2026-11-04 `/green` Green — skill, e2e, docs, changelog · green commit `9c8a8e0`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
