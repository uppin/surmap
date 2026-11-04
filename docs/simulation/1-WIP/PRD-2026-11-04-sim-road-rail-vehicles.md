# Road and rail vehicles that drive - PRD

**Date**: 2026-11-04
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md))
- **Related Feature**: [Survey agent](../../agent.md) — Simulation tools

## Summary

A scenario can hold cars, buses, trucks and trains that drive: each is a `vehicle` element of a
class, drawn by a pinned CC0 glTF, moved by the behaviour tree people already use, with
acceleration, braking and turning limited the way a real vehicle's are. Trains run as a
locomotive and carriages along their track. Their tracks are layered ground truth for the survey.

## Proposed Changes

### What's Changing

- A `vehicle` element (`class`: `car`, `bus`, `truck`, `train`) with an optional `behaviour` tree,
  `glb` override and, for trains, `cars`.
- Class presets `assets/vehicle/<class>.vehicle.json`: glTF, length/width/height, wheel nodes,
  max speed, acceleration, braking, turn rate, carriage glTF and spacing.
- Vehicle kinematics on top of the tree: speed eases to the node's `speed_m_s` within the class's
  limits; heading turns at most at the class's rate; wheels spin with distance travelled.
- `object_tracks.jsonl` lines gain `kind` and `yaw_deg` per object; moving vehicles appear there,
  never in `ground_truth.json`.
- Station: `vehicle` validated like the renderer does; the agent's `add_element` takes a vehicle;
  preset `street-traffic`.

### What's Staying the Same

Manifest version 1; every existing scenario renders as before. Passive survey only — nothing
here moves the drone; moving vehicles are never fused into the static scene or RTAB-Map's map.

## Acceptance Criteria

1. A vehicle following a path never exceeds its class's speed, acceleration or turn rate, and
   reaches the path's end; the same scenario replays the same track.
2. A train's carriages stay on the locomotive's path at the class spacing.
3. A capture of `street-traffic` records every moving vehicle per frame with its kind and heading,
   and `ground_truth.json` holds none of them.
4. The agent adds a vehicle through `add_element`; an unknown class or an invalid tree is refused
   with the reason, by the station and by the renderer alike.
5. A native still of `street-traffic` shows the vehicles on the avenue and the train on its track.
