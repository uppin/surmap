# PRD: Simulation based on the map (map floor)

**Date**: 2026-11-04 · **Stack**: `#map-floor` (#127–#131)

## Problem

Simulated scenes are fictional blocks on procedural ground. A survey rehearsed in the
simulation therefore cannot be rehearsed *where it will happen*: the streets, blocks and
landmarks the team will see are not in the scene, and objects are placed by eye in ENU
metres with no relation to GPS.

## Goal

The agent sends the map layer, cropped to a specific GPS area, to the WASM simulation,
which renders it as the floor of the scene; the agent then adds 3D objects on top, placed
by GPS.

## Requirements

1. The agent names a GPS bounding box (SW + NE corners, ≤ 1 000 m a side). The station
   stitches OpenStreetMap raster tiles cropped to that box into one texture and the
   scenario records it (`map_floor`). Tiles are disk-cached; the tile server is
   configurable (`SURMAP_TILE_URL_TEMPLATE`, `SURMAP_TILE_CACHE_DIR`) for offline use.
2. The WASM renders the texture as the scene's floor: the preset ground is replaced (not
   covered), and the floor carries the fixed collider the scene stands on.
3. The agent places objects by GPS through a tool (`geo_to_enu` / `enu_to_geo`), never by
   doing conversion maths itself. The ENU origin is the bbox centre.
4. The agent knows the feature exists: the scene-building skill describes the flow, the
   warnings (re-anchoring moves placed elements; elements outside the floor), and
   `clear_map_floor`.
5. © OpenStreetMap contributors is credited in the scenario's credits and the docs.

## Settled decisions (review, 2026-11-04)

- Texture cap: zoom ≤ 18, ≤ 64 tiles, stitched texture ≤ 4 096 px a side (`choose_zoom`
  picks the sharpest zoom satisfying all three).
- Floor textures are shared, not per-scenario: the PNG lives in the station library under
  its content hash (`library/map-floor/<sha256>.png`); scenarios reference the path.
- The floor is flat and printed: no ground depth for the stereo rig; placed objects
  supply the 3D. Out of scope: extruded Overture buildings, terrain elevation.

## Acceptance

- An agent turn on a real socket bases a scenario on a bbox, converts a GPS target
  through the tool, places a building there; the station serves the manifest and the
  floor PNG; the floor is visible and collidable in the renderer (cargo tests for the
  collider/ground-hiding; a native screenshot remains the one manual check).
