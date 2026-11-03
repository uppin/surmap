# Behaviour trees for simulation objects and the wind - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md))
- **Related Feature**: [Survey agent](../../agent.md) — Simulation tools

## Summary

People in a scenario act by behaviour trees the agent declares and edits — wander, follow a path,
flee a fire — and the wind follows its own tree, so a scenario's wind can veer and strengthen over
time and the vegetation, fire and smoke follow it. The trees are JSON in the scenario; their
tracks are recorded as ground truth.

## Proposed Changes

### What's Changing

- A `behaviour` tree on `person` elements and on `weather.wind`; a deterministic runtime.
- Tools `set_behaviour`, `update_behaviour_node`, `get_behaviour`; preset `wildfire-evacuation`.
- Captures carry `object_tracks.jsonl` (positions, running action, wind per frame).

### What's Staying the Same

Passive survey only; moving objects are never fused into the static scene or RTAB-Map's map.

## Acceptance Criteria

1. The agent sets and edits trees through tools; invalid trees are refused with the reason.
2. A person fleeing a wildfire never stands inside its burnt area; runs are deterministic.
3. A wind tree changes the wind over time, and the change reaches everything n3 drives with it.
4. Captures record each person's track and the wind per frame.
5. The B1 checkpoint passes the planner's review.
