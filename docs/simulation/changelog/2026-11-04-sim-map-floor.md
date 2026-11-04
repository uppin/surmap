# Simulation based on the real map: an OpenStreetMap floor the agent builds on

**Date:** 2026-11-04
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · Survey agent simulation tools ([agent.md](../../agent.md)) · PRs #127–#131 (`#map-floor`)

A scenario can now be based on the real map. `set_map_floor` takes a GPS bounding box
(SW + NE corners, at most 1 000 m a side); the station stitches OpenStreetMap raster
tiles cropped to the box into one PNG and the manifest gains `map_floor {sw, ne,
texture, zoom}`. Tiles come through a `TileSource` port (OSM adapter, in-memory test
adapter), are disk-cached under the library's `tile-cache/`, and the tile server is
configurable via `SURMAP_TILE_URL_TEMPLATE` / `SURMAP_TILE_CACHE_DIR`. The stitched
texture — zoom ≤ 18, ≤ 64 tiles, ≤ 4 096 px a side — is shared between scenarios under
its content hash, and © OpenStreetMap contributors is credited in the scenario's
credits.

The floor replaces the preset ground: `set_map_floor` removes the `ground` box (its
opaque top would hide the floor), `clear_map_floor` restores it, and the renderer gives
the floor plane a fixed collider whose top is at 0 m, so people, vehicles and nests
stand on it. The ENU origin is the bbox centre (the semantic snapshot's rule), and the
agent never converts GPS itself: `geo_to_enu` / `enu_to_geo` translate through the
tool, `set_map_floor` warns when re-anchoring moves placed elements or leaves one
outside the floor, and the scene-building skill teaches the flow. The floor is flat
and printed — it gives the stereo rig no ground depth; the placed 3D objects supply
the depth. Verified by handler tests over fake tiles, a shared Python/Rust golden
manifest, cargo tests for the collider and ground-hiding, and an agent turn on a real
socket that bases a scene on a bbox and places a building by GPS.
