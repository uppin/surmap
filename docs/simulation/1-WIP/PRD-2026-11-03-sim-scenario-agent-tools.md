# Simulation scenarios built by the survey agent - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: [Survey agent](../../agent.md) — new `SimulationTools`
- **Related Feature**: Bevy disaster simulation (`examples/bevy-sitl-poc`, PR #89)

## Summary

The survey agent can build the world it is about to survey: it searches three free asset sources,
downloads licence-compatible models and textures into the station, composes a disaster scenario
(earthquake, flood, wildfire) with rain, fog and animated fire and smoke, and publishes it for the
browser simulation to load — no rebuild.

## Background

Developer request (2026-11-03): tools for the agent to create simulations for various scenarios,
search and download GLB assets, declarative rain, fog and fire — "it should be able to simulate
wild-fires with fire and smoke (animated)"; the station's SQLite database backs the RPC.

## Proposed Changes

### What's Changing

- `SimulationTools` agent tools on the station: asset search across Sketchfab (CC0/CC BY),
  Poly Haven and ambientCG; download with licence gate and attribution; scenario create, edit
  (models, weather, fires), get, list, publish.
- A station SQLite store for the asset catalogue, files, attributions and scenarios.
- Scenario JSON (extends #89's manifest) with `weather`, `fires`, `credits`; `?scenario=<id>`.
- Animated wildfire (spreading front, flames, embers, smoke), rain, fog in the simulation.

### What's Staying the Same

- #89's scene, stream and bridge; the survey tools; scope boundary — the agent builds simulated
  worlds only, never commands a drone.

## Acceptance Criteria

1. A scripted agent session builds and publishes `wildfire-edge` through the tools only; the page
   loads it and shows a spreading fire with smoke (screenshots t = 0/30/90 s).
2. Assets licensed NC, ND, SA or non-CC are refused with the reason; CC BY assets appear in the
   scenario's credits and the page's credits panel.
3. Every downloaded file has its SHA-256 in the store; nothing downloaded is committed.

## Status

🚧 In Progress
