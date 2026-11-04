# Simulated drones on their nests, flown by a kinematic autopilot - PRD

**Date**: 2026-11-04
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md))
- **Related Feature**: Bevy captures for RTAB-Map ([bevy-simulation.md](../bevy-simulation.md) § recording)

## Summary

Every nest in a scenario now holds its drones, docked on the pad. A drone flies only when it is
told to: it takes off, flies its route on a kinematic autopilot, and can be re-routed mid-flight,
sent on a detour, or recalled to land on its nest. Several drones can fly at once. Exactly one is
**active**. Its stereo eyes are the ones rendered to the feed panel and recorded, the chase camera
follows it, and the status line describes it.

The commands come from a **fleet log**: each command is stamped with the simulation time at which
it took effect. The autopilot is a pure function of (nest, log, time), so a recorded or replayed
session gives the same frames every time. This PR reads the log from a file (`--fleet-log`). The
next PR fills it live from the station.

## Proposed Changes

### What's Changing

- **Docked drones.** For each nest, its `drones` drone bodies sit on the pad, facing the pad's
  heading. They are named `<nest>-d1 …`.
- **Commands**, carried by the fleet log:
  - `launch` (route) — take off vertically, then fly the route.
  - `set_route` (route) — replace the rest of the route from where the drone is.
  - `detour` (waypoints) — fly these first, then resume the waypoint the drone was heading to.
  - `recall` — fly back over the nest, descend and land.
  - `set_active` — this drone's eyes become the feed.
- **A route** is waypoints in ENU metres, a speed (default 5 m/s, at most 8), and what to do at the
  end: `return` to the nest (default) or `hover` in place.
- **Flight limits.** The autopilot keeps every drone within 8 m/s horizontal, 2.5 m/s²
  acceleration, 2 m/s climb or descent and 60°/s yaw. A command never makes a drone jump: it
  turns, slows and climbs from where it is.
- **Refused commands.** A command that cannot apply in the drone's current phase is refused and
  logged as refused, never half-applied. Examples: launching a drone already in flight, a detour
  for a docked drone, an empty route, a speed outside 0.5–8 m/s, a waypoint below 5 m or above
  60 m.
- **The active drone** drives everything that today follows "the drone": the LEFT/RIGHT feed
  panel, the chase camera, the status line and the recorder's frames and `pose_enu`. The status
  line also lists every drone with its phase (`DOCKED`, `CLIMBING`, `CRUISING`, `DETOUR`,
  `HOVERING`, `RETURNING`, `LANDING`).
- **Recordings** of a fleet scenario carry the active drone's id on every frame
  (`frames.jsonl` `drone_id`). The station's capture loader reads it.
- `--fleet-log <file>` replays a log natively (stills and `--record`).

### What's Staying the Same

- A scenario with no nests behaves exactly as today: one drone, keyboard flight, and the scripted
  `survey-loop` for stills and recordings.
- Calibration, the wire format and the capture layout are unchanged (`drone_id` is an extra,
  optional key).
- SurMap's survey pipeline only consumes the active drone's frames; nothing is fed back.

## Acceptance Criteria

1. A launched drone climbs vertically from its pad, then reaches each waypoint (within 1 m) in
   order. Its speed, climb rate and turn rate stay within the limits throughout.
2. A `set_route` mid-flight changes course from the drone's current position, with no jump.
3. A `detour` visits its waypoints, then resumes the waypoint that was next.
4. A `recall` (or the end of a `return` route) lands the drone back on its own pad, and it ends
   `DOCKED`.
5. Two drones fly at once without affecting each other's paths.
6. The same log and time give the same pose for every drone; a recording replays frame-identical
   poses.
7. After `set_active`, the recorded frames carry the new drone's id and pose.
8. A refused command leaves the drone's flight unchanged and is reported with the reason.
9. A scenario without nests records the same `survey-loop` frames as before.

## Out of Scope

- The live link from the station (n3), the agent's tools (n4), and per-drone perception (n5).
- Obstacle avoidance and collision between drones. Routes are flown as given; the agent plans
  around buildings. This is recorded as a follow-up TODO.
- Battery, wind drift on drones, and failure modes.
