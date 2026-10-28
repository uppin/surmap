# Disaster-response Gazebo world - PRD

**Date**: 2026-10-28
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: [PX4 SITL session bridge](../px4-sitl.md) — the bridge can already record any world; this adds the world the demo flies and the scoring file for that recording
- **Related**: [Architecture §2.3 / §4.3](../../../architecture.md) — Machine 3 gains a named disaster scene and ground truth

## Summary

A fictional civilian search-and-rescue block in Gazebo Harmonic, with ground-truth person and road positions and a lawnmower plan the operator loads. SurMap still does not fly the vehicle.

## Background

The hackathon demo (civilian disaster response, deadline 4 Nov) needs imagery of an urban block after an earthquake and a flood: collapsed and standing buildings, blocked and open roads, cars, and people a detector and SAM can see. PR #18 launches a stereo x500 into PX4's empty default world.

## Proposed Changes

### What's Changing

- New world `disaster_block` the existing `x500_surmap_stereo` airframe spawns into
- Ground-truth JSON in map ENU and WGS84, from the world's spherical coordinates
- A QGroundControl survey plan at 12 m that covers the block
- One launch command, plus WSL2 / WSLg steps so the Gazebo GUI is visible
- Asset list and licences in `docs/simulation/disaster-world.md`

### What's Staying the Same

- SurMap publishes no flight commands, setpoints, or mission items
- Stereo model, capture dump, and EuRoC export from PR #18
- README.md is not edited

## Impact Analysis

### Technical Impact

- New loader in `surmap.simulation` and static assets under `docs/simulation/gz/worlds/`
- Launch depends on a local PX4 checkout (`~/PX4-Autopilot`) the same way the existing runbook does
- No new Python dependency

### User Impact

- Operators symlink the world (the launch script does it) and start SITL with one command
- They upload the plan from QGroundControl when they want the lawnmower
- Scoring code reads the JSON; it is not a flight interface

## Implementation Plan

1. Failing tests for the anchor, the survivors, the roads, the SDF poses, and the plan
2. World, textures, JSON, plan, loader, launch script
3. Wrap the runbook into `docs/simulation/disaster-world.md` and point architecture and `px4-sitl.md` at it

## Acceptance Criteria

- The world shows intact and partly collapsed buildings, rubble, a tilted slab, debris, a fallen pole, a flooded road section, parked and overturned cars, and standing, lying, and waving people
- Only freely licensed assets are used, and the runbook lists sources and licences
- Ground truth gives map-frame and lat/lon positions from the world's spherical coordinates
- A lawnmower plan covers the block at a documented altitude
- One command starts PX4 SITL in this world with the stereo airframe
- WSL2 / WSLg steps show the Gazebo GUI
- CI lint and tests stay green without launching Gazebo

## References

- [Changeset](./2026-10-28-disaster-gazebo-world.md)
- [px4-sitl.md](../px4-sitl.md)
