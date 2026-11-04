# Changeset: Simulation map floor — tile stitching

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — cross-language manifest parity, a network port, and a renderer surface

## Summary

`surmap.simulation.map_floor`: a GPS bbox becomes a floor texture. A `TileSource` port
(hexagon shape, as `surmap.slam`) with an OSM native adapter and an in-memory test adapter;
slippy-tile stitching cropped to the bbox; geodesy that inverts the semantic snapshot's
ENU rule. Tiles are disk-cached (`<z>/<x>/<y>.png`), the URL template is the station map's
own OSM layer (configurable via `SURMAP_TILE_URL_TEMPLATE` / `SURMAP_TILE_CACHE_DIR`), and
`choose_zoom` picks the sharpest zoom inside all three caps: zoom ≤ 18, ≤ 64 tiles,
≤ 4 096 px a side. The PNG is named by its content hash, so scenarios share one texture.

## Stack Context

**Stack**: `#map-floor` — **2 of 5** · **Branch**: `pr-2-map-floor-tiles` · **Base**: `pr-1-map-floor-manifest`
**Kind**: Feature · behaviour-adds · **Workflow**: preset `feature`

### Green wave

**Wave:** 1 of 3 · **Node:** n1 · **Blocks:** n3 (the tool stitches through this port)

### Greenable independently?

**yes** — stitching and geodesy are pure over the fake adapter.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `map_floor` manifest shape | #127 | implemented below | produces the texture path it records; does not edit manifests |

## Verification

V1 executed: geodesy round-trip, bbox refusals, deterministic stitch, disk cache serves
the second fetch without HTTP, pixel cap. All green, no network in any test.

## Prerequisites

As #127. **Outcome:** none blocking.

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset and discovery · this file
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — failing tests · red commits
- [wf 3] ✅ 2026-11-04 `/green` Green — stitch, cache, shared URL, pixel cap · green commits
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
