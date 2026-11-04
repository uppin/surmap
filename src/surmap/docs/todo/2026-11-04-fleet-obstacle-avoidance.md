# 2026-11-04 — The fleet autopilot neither avoids obstacles nor separates drones

**Category:** Future enhancement
**Source:** PR #117, stack `drone-fleet` n2 (2 of 5), Wrap row `[wf 4]`, which the changeset's *Decisions & Trade-offs* planned
**Packages:** examples/bevy-sitl-poc, src/surmap
**Consent:** PRD `fleet-autopilot` non-goal ("Obstacle avoidance and collision between drones … recorded as a follow-up TODO")
**Priority:** 4
**Status:** Open
**Plan:** ⚠️ recorded debt, no PR planned

## What is left

The kinematic autopilot (`examples/bevy-sitl-poc/src/fleet/autopilot.rs`) flies every route
exactly as given. A route through a building passes through it, and two drones on crossing
routes can occupy the same point. Nothing detects or refuses either case.

## Why it could not be done now

Avoidance would turn the autopilot into a path planner, which is much more than the
`#drone-fleet` stack needs. The stack only needs a deterministic, replayable flight that the agent
tasks.

## What was done instead

The agent has to plan routes around buildings (`docs/simulation/bevy-simulation.md`
§ *The fleet and its autopilot*). Waypoint altitude is limited to 5–60 m, and the log refuses
invalid commands.

## When picked up

There are two options. One is to refuse, at `FleetLog::push`, a route segment that crosses a
building footprint or comes within a separation radius of another drone's planned path. The other
is to add a local avoidance layer to `Autopilot` that keeps `state_at` pure.
