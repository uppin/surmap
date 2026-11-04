# The fleet link: the station commands the running simulation's drones - PRD

**Date**: 2026-11-04
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md))
- **Related Feature**: Survey agent server ([agent.md](../../agent.md)) — `/sim/` hosting

## Summary

The simulation page and the station talk while the simulation runs. A page opened with `?fleet=1`
connects to the agent server it was served from. Over that link:

- the station sends fleet commands (launch, new route, detour, recall, set active);
- the simulation answers each one with *applied at simulation time t*, or *refused, because…*;
- twice a second it reports every drone's phase and position.

The station keeps the applied commands as the session's fleet log. The same log can be replayed
natively with `--fleet-log`, so a live session can be recorded again frame for frame.

This is the transport and its gatekeeper. The agent's tools that use it come in the next PR.

## Proposed Changes

### What's Changing

- **A WebSocket at `/sim/fleet?scenario=<id>`** on the agent server, beside the existing `/sim/`
  routes. It speaks `fleet/v1`: JSON messages `hello`, `command`, `applied`, `refused`,
  `telemetry`. Byte-exact examples are shared by the Rust and Python tests.
- **The station's fleet controller**, one per scenario:
  - **Before sending**, it refuses what can never apply: an unknown drone, a waypoint outside the
    scene bounds or outside 5–60 m up, a speed outside 0.5–8 m/s, an empty route, or a command
    that does not fit the drone's last reported phase.
  - **After sending**, it waits up to 5 s for the simulation's answer.
  - It reports *no simulation connected* when no page is linked.
  - It keeps the latest telemetry and the applied log.
- **The applied log is stored with the scenario**, one log per simulation session, and exports as
  the `--fleet-log` file.
- **The page with `?fleet=1`** opens the link, applies commands at the current simulation time and
  sends telemetry. Without the parameter, nothing connects.
- **A smoke script**, `scripts/fleet_link_smoke.py`, starts the agent server, waits for a page to
  link, flies a scripted sortie through the controller, and prints every answer. It is the manual
  check for the browser side.

### What's Staying the Same

- Frames still never leave the page over this link. Streaming the active drone's frames is n5's
  work, on the stereo bridge.
- A page opened without `?fleet=1`, and every native run, behave as before.
- The link carries simulation commands only. There is no path from it to PX4 or any flight
  controller (`docs/architecture.md` §1).

## Acceptance Criteria

1. A linked simulation receives a valid command and answers *applied* with its simulation time.
   The controller returns that time, and the command appears in the scenario's stored log.
2. A command the simulation refuses comes back as *refused* with the simulation's reason, and is
   not logged as applied.
3. The controller refuses invalid commands without sending them, naming the rule.
4. With no page linked, a command fails with *no simulation connected for scenario X*. A linked
   page that does not answer within 5 s fails with a timeout.
5. Telemetry from the page is what the controller reports as each drone's phase and position.
6. A second page linking the same scenario is refused while the first is connected.
7. The stored log exports as a `--fleet-log` file that the renderer parses.
8. In Chrome, `/sim/?scenario=<earthquake-fleet>&fleet=1` links, and the smoke script's sortie
   flies on screen (V4 procedure, recorded).

## Out of Scope

- The agent's fleet tools (n4) and per-drone perception (n5).
- Authentication of the link. It binds wherever the agent server binds; the server's own
  deployment rules apply.
- More than one simulation page per scenario.
