# Drone nests the agent places, and the simulation-only fleet exception - PRD

**Date**: 2026-11-04
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md))
- **Related Feature**: [Survey agent](../../agent.md) — Simulation tools
- **Related Feature**: [Architecture §1 scope boundary](../../architecture.md)

## Summary

A scenario can hold **drone nests**: docking pads scattered across the scene, each housing one to
four simulated drones. The survey agent decides where they go, using the same `add_element` call
it uses for buildings and people. Placements that could never work are refused with the reason:
inside a building, on water, off the ground, or crowded against another nest.

This PR also writes down the developer's scope decision of 2026-11-04. On the simulation machine
only, the agent may task the simulation's own drones; the next PRs of this stack build that
tasking. SurMap still has no write path to PX4 or any real flight controller, and the survey
pipeline stays a passive consumer of whichever feed it is given.

## Proposed Changes

### What's Changing

- **New element kind `drone_nest`** in the scene manifest:
  `{"kind": "drone_nest", "id": "nest-north", "position_enu": [x, y, z], "yaw_deg": 0, "drones": 2}`.
  - `drones` is 1–4 and defaults to 1.
  - The nest's drones are named `<nest-id>-d1` … `<nest-id>-dN`. Those names join the manifest's
    single id namespace, so they may not collide with any other id.
- **Placement rules**, refused identically by station and renderer:
  - The 2.4 m × 2.4 m pad sits within ±500 m east/north of the origin and 0–60 m up.
  - It may not overlap a building, collapsed building or solid box footprint unless it stands on
    that element's top (a rooftop nest).
  - It may not overlap a `water: true` surface.
  - Nest centres are at least 6 m apart.
  - A scenario holds at most 8 nests.
- **The renderer draws each nest** as a landing pad (a square pad with an "H" marking and a dark
  rim), turned by `yaw_deg`. No drone sits on it yet; the next PR docks them.
- **The agent places nests** with `add_element` and a `drone_nest` element. The scene-builder
  subagent's procedure says when and how to place them.
- **Preset `earthquake-fleet`**: the earthquake block with three nests. Two are on open ground at
  opposite corners, and one is on a standing building's roof.
- **Scope amendment**:
  - `docs/architecture.md` §1, §2.3 and §4.3, `AGENTS.md`'s scope guardrail and `README.md` gain
    the simulation-only exception.
  - The exception is a new row of the scope table. The agent may task *simulated* drones on
    machine 3. Real flight control, PX4 commands and any interface to a flight controller stay out
    of scope.

### What's Staying the Same

- Every existing scenario renders as before; a scenario with no nests has no nests.
- The single scripted drone and its `survey-loop` are unchanged in this PR.
- Moving objects are never fused into the static scene; object points stay layered on RTAB-Map's
  output.

## Acceptance Criteria

1. The agent adds a `drone_nest` to a scenario, and the stored manifest validates in Python. The
   Rust renderer parses the same manifest (shared golden `fleet-nests.json`).
2. A nest inside a building footprint, on water, outside the bounds, within 6 m of another nest,
   with `drones` outside 1–4, or whose drone id collides with another id is refused. The refusal
   names the nest and the rule, and is the same from station and renderer.
3. A nest on a building's roof (z at the roof top) is accepted.
4. The `earthquake-fleet` preset creates a valid scenario with three nests and five drones.
5. `docs/architecture.md`, `AGENTS.md` and `README.md` state the simulation-only exception and
   keep "no write path to any real flight controller".

## Out of Scope

- Drones on the nests, flight and the autopilot (n2 of `#drone-fleet`).
- The live link, the agent's fleet tools, and per-drone perception (n3–n5).
- Nests on real hardware or any real dock integration.
