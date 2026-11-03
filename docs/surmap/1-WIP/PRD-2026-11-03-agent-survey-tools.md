# Survey agent — SurMap tools - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Survey agent (new, `docs/agent.md` created at wrap) — what the agent can do
- **Related Feature**: Demo console (`scripts/demo.py`, `docs/viewer.md`) — runs started by the agent
  are ordinary runs in the same history database

## Summary

Implement the `SurveyTools` proto service so the agent can list and run demos, prompt SAM, find the
objects SAM detected with their 3D summaries and geometry, and fetch raw or cropped frames.

## Background

These are the capabilities the developer asked the agent to have. Every tool only reads or starts
demo/replay runs — nothing commands a vehicle (AGENTS.md scope guardrail).

## Proposed Changes

### What's Changing

| Tool | Does | Default execution |
|---|---|---|
| `list_demos` | scenes from the catalogue, default SAM prompt, prepared or not, cached recording id | SYNC 10 s FAIL |
| `run_demo` | prepares the scene if needed, starts a headless run with a SAM prompt, frame limit and fps; returns run id, frame count, object count when it ends | SYNC 30 s DETACH |
| `get_run` | status, scene, prompt, frames, objects, timestamps of a run | SYNC 10 s FAIL |
| `prompt_sam` | runs SAM with a text concept on chosen frames of a recorded run (default: evenly spaced, ≤ 8), returns detections with boxes, scores, mask polygons and an id per detection | SYNC 60 s DETACH |
| `find_objects` | objects of a run filtered by label text, near a point (radius), moving or static; returns `ObjectSummary`s sorted by distance or size | SYNC 15 s FAIL |
| `get_object` | one object's `ObjectSummary` with neighbours | SYNC 10 s FAIL |
| `get_object_geometry` | `surmap-obj v1` text (limits adjustable) and a `geometry_uri` to its GLB | SYNC 15 s FAIL |
| `get_frame` | a run's frame by index, frame id or `t_ns`; full resolution when the scene cache has it, else the recorded display JPEG; optional crop by pixel box or by object id (its mask's box, padded); optional max side; returned as an image the model sees | SYNC 15 s FAIL |

### What's Staying the Same

- Demo server behaviour and its HTTP API; recorded runs; SAM adapters.

## Impact Analysis

### Technical Impact

Uses `DemoRunHost` (n2) without HTTP; reads `RunHistoryStore`; SAM through the existing detector
factories (`--sam-fake` style fake in tests).

### User Impact

The agent can answer "run the KITTI demo looking for cars and show me the largest one".

## Implementation Plan

See the changeset `2026-11-03-agent-survey-tools.md`.

## Acceptance Criteria

1. `list_demos` lists the three scenes with their default prompts.
2. `run_demo` on the tiny EuRoC fixture with a fake SAM finishes and `get_run` reports its frames
   and objects.
3. `prompt_sam` on a recorded run returns detections from the fake detector for the chosen frames.
4. `find_objects(label="box")` returns summaries; `near` filters by distance.
5. `get_object_geometry` returns OBJ text within the limits and a GLB URI that resolves.
6. `get_frame` with a crop returns a JPEG of the crop's size; with `object_id` the crop contains the
   object's mask box.

## References

### Affected Features (Complete List)

- Survey agent (new); Demo console
