# Rigged, animated people - PRD

**Date**: 2026-11-04
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md))
- **Related Feature**: [Survey agent](../../agent.md) — Simulation tools

## Summary

People in a scenario stop being a capsule and a sphere: each is a rigged CC0 human glTF that
walks and runs with its feet matching its speed, and can be posed the way a survey finds people
after a disaster — lying injured, sitting, waving for help. Body height and coat colour vary per
person. Everything stays manifest data; behaviour trees still decide where people go.

## Proposed Changes

### What's Changing

- The figure (`assets/behaviour/person.figure.json`) names a rigged glTF and its clips (idle,
  walk, run, wave, sit, lie) with each locomotion clip's ground speed; the capsule figure stays as
  the fallback until (or if) the glTF loads.
- A `person` takes optional `pose` (`standing` · `lying` · `sitting` · `waving`), `height_m` and
  `glb`.
- Locomotion: idle → walk → run blended by speed, played at speed / clip ground speed so feet do
  not slide; the clip clock is simulation time, so stills and recordings are reproducible.
- `object_tracks.jsonl` objects that are people carry their `pose`.
- Station: pose/height validated; `add_element` person takes them; preset `earthquake-survivors`.

### What's Staying the Same

Behaviour trees, their tick, and every existing scenario (a person with no `pose` stands, as
today). Passive survey only; moving people are never fused into the static scene.

## Acceptance Criteria

1. A walking person plays the walk clip at a rate matching its speed; above the run threshold it
   runs; standing it idles; with a pose and no motion it holds that pose.
2. The same scenario at the same simulation time renders the same skeleton pose.
3. A lying person's ground-truth extent is lying (long axis horizontal) in captures' tracks.
4. Invalid poses or heights are refused with the reason by station and renderer alike.
5. Native stills of `earthquake-survivors` (`people.png`, `person-close.png`) show recognisable
   people: one lying, one sitting, one waving, rescuers walking.
