# The survey agent flies the simulation's fleet - PRD

**Date**: 2026-11-04
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: [Survey agent](../../agent.md) — a new `FleetTools` service
- **Related Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md)) — the fleet link

## Summary

The survey agent can now run a simulated drone operation from the chat. It can:

- see where the scenario's nests are and what every drone is doing;
- launch a drone with a planned route;
- change a drone's route mid-flight or send it on a detour;
- recall it;
- choose which drone's camera is the one on screen.

Every command goes to the running simulation page through the fleet link, and the agent hears
back exactly when it took effect or why it was refused. These tools exist only for the
simulation. The agent is told so, and asked to fly a real aircraft it still says it cannot.

## Proposed Changes

### What's Changing

- **New tools**, one rpc each in `FleetTools`:

  | Tool | What it does |
  |---|---|
  | `list_nests` | each nest's id, position, heading and drone ids |
  | `list_drones` | whether a simulation page is linked, its simulation time, the active drone, and each drone's nest, phase, position, heading, speed and remaining waypoints |
  | `launch_drone` | a docked drone takes off and flies a route: waypoints in ENU metres, an optional speed and `return` or `hover` at the end |
  | `set_route` | replace an airborne drone's remaining route |
  | `add_detour` | fly these waypoints first, then resume |
  | `recall_drone` | return to the nest and land |
  | `set_active_drone` | this drone's camera becomes the feed |
  | `get_fleet_log` | the session's applied commands, as the replay file |

- **Answers.** Each command answers with the simulation time it took effect and its sequence
  number, or with a precise failure:
  - an unknown drone or scenario;
  - an invalid route (and which rule it breaks);
  - the drone's phase does not allow it;
  - no simulation page is linked;
  - the page did not answer in time.
- **A procedure skill, `flying-the-fleet`.** It covers planning a route over the scene (clear of
  buildings, 5–60 m up), checking with `list_drones`, detours for a closer look, and switching the
  active drone to the one whose view matters.
- **The agent's instructions** say the fleet tools task simulated drones only. The map skill's
  wording ("no map tool commands a vehicle") points to the fleet tools for simulated drones, and
  still refuses real aircraft.

### What's Staying the Same

- Map routes stay display-only drawings. Simulation tools still build scenes. Survey tools still
  run datasets.
- There is no tool and no path that reaches PX4 or a real flight controller.

## Acceptance Criteria

1. With a linked simulation, the agent's `launch_drone` call flies the drone. The tool result names
   the simulation time it took effect, and `list_drones` then reports it climbing or cruising.
2. `set_route` and `add_detour` on an airborne drone take effect; on a docked drone they fail,
   naming the phase.
3. `recall_drone` ends with the drone docked (as `list_drones` reports).
4. `set_active_drone` is acknowledged, and `list_drones` reports the new active drone.
5. Without a linked page, every command fails with "no simulation connected", and `list_drones`
   reports `linked: false`.
6. Invalid routes are refused before reaching the simulation, naming the rule.
7. A scripted model conversation through the real agent server uses `list_nests`, `launch_drone`,
   `add_detour` and `set_active_drone` in turn and gets those answers.

## Out of Scope

- Per-drone mapping and segmentation status (n5 adds `drone_map_status` to this service).
- Mirroring routes and drone positions onto the chat map (a follow-up TODO).
- Automatic mission planning. The agent plans routes from the scene with its own judgement.
