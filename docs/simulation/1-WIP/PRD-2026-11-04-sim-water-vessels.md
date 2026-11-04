# Boats and ships on the water - PRD

**Date**: 2026-11-04
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md))
- **Related Feature**: [Survey agent](../../agent.md) — Simulation tools

## Summary

Boats and ships join the vehicles: they float at the water's surface, heave, pitch and roll with a
sea state driven by the scenario's wind (a small boat rocks, a ship barely moves), and steer along
behaviour-tree paths that stay on the water. A flood-rescue scenario puts rescue boats in a
flooded street.

## Proposed Changes

### What's Changing

- Vehicle classes `boat` and `ship` (`assets/vehicle/boat.vehicle.json`, `ship.vehicle.json`,
  `medium: water`), pinned CC0 glTF.
- A `box` element may be marked `"water": true` — a water surface vessels float on.
- Wave motion: heave, pitch and roll from the weather's wind and the vessel's length, seeded per
  id, on simulation time.
- A vessel must start on water and every point its tree steers to must be on water; vessel trees
  may not `wander` or `flee_from_fire`.
- Tracks carry boats and ships (`kind` `boat`/`ship`); station validation, `add_element` classes,
  preset `flood-rescue`.

### What's Staying the Same

Road and rail vehicles, people, existing water boxes (unmarked water renders as before).

## Acceptance Criteria

1. A vessel stays at its water surface (± its heave) for a whole run; stronger wind rocks it more;
   a ship rocks less than a boat in the same wind; the same scenario replays the same motion.
2. A vessel that starts off water, or whose path leaves water, is refused with the reason by the
   station and the renderer.
3. A capture of `flood-rescue` tracks the boats per frame; `ground_truth.json` lists none.
4. A native still of `flood-rescue` shows the boats on the flooded street.
