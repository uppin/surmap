# Weather, wind-swept vegetation and an animated wildfire - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md))
- **Related Feature**: [Survey agent](../../agent.md) — Simulation tools

## Summary

Scenarios gain weather (rain, fog, wind), stands of pines and grass that sway in that wind, and
wildfires whose front spreads downwind as an animated fire with flames, embers and smoke that bend
with the same wind. The agent declares all of it through tools; the fire's perimeter is recorded as
ground truth.

## Proposed Changes

### What's Changing

- Manifest `weather`, `fires` and a `vegetation` element kind; presets `wildfire-edge`, `flood-street`.
- Rendering: Feronia wind-swept pines and grass (from the developer's FeroniaDemo), GPU particles
  (`bevy_hanabi`) for flames, embers, smoke and rain, burnt ground behind the front.
- Tools `set_weather`, `add_fire`, `remove_fire`.
- Captures carry `fire_perimeter.jsonl`.

### What's Staying the Same

The renderer's camera profile, stereo stream and recorder format (one file added); the station's
store and serving; passive survey only — the fire is simulated, nothing commands a vehicle.

## Acceptance Criteria

1. The fire model: zero wind → a circle growing at `spread_m_s`; with wind the front reaches farther
   downwind than upwind, never past `max_radius_m`, and nothing burns before `start_s`.
2. One wind drives the vegetation, the spread, flame lean and smoke drift.
3. The agent builds `wildfire-edge` through tools; the renderer accepts the scenario the store writes.
4. A capture of a burning scenario records the perimeter per frame.
5. The screenshot checkpoints pass the planner's review against the visual spec.

## Status

🚧 In Progress
