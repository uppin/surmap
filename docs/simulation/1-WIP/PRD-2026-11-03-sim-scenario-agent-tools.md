# Simulation scenarios built by the survey agent (station side) - PRD

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

### What's Changing (this PR, stack node n2)

- `SimulationTools` agent tools: search three free asset sources (Poly Haven, ambientCG,
  Sketchfab filtered to CC0 / CC BY), download licence-accepted assets into the station's
  library, compose scenarios from #89's element kinds and downloaded models, list and get them.
- A station SQLite store: asset catalogue, files with SHA-256, every scenario edit as a version.
- The agent server serves the simulation page, every scenario's latest version and the library
  under `/sim/`; the page's `?scenario=<id>` loads it — no rebuild, same origin.

### Next in the stack

- n3: weather and an animated wildfire (fire, smoke, embers, rain; burnt ground; fire-perimeter
  ground truth) and the tools that declare them.
- n4: behaviour trees for objects, defined and changed by the agent.

### What's Staying the Same

- #89's renderer and element kinds; the survey and map tools; scope boundary — the agent builds
  simulated worlds only, never commands a drone.

## Acceptance Criteria

1. A scripted agent session builds a scenario through the tools only, and the station serves it
   at `/sim/assets/scenarios/<id>.json` with the downloaded model's library path.
2. NC / ND / SA and non-CC assets are refused with the reason; CC BY assets appear in the
   scenario's credits.
3. Every downloaded file has its SHA-256 in the store and is served byte-identical; nothing
   downloaded is committed.

## Status

🚧 In Progress
