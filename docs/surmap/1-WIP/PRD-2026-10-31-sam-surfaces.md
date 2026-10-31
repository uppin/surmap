# SAM surfaces — region points assigned to persistent object surfaces — PRD

**Date**: 2026-10-31
**PRD Type**: Enhancement
**Status**: 🚧 In Progress
**Changeset**: [2026-10-31-sam-surfaces.md](./2026-10-31-sam-surfaces.md)

## Affected Features

- **Primary**: Station-side fusion (`src/surmap/survey/surfaces.py`, new) — every dense region
  point is assigned to one object *surface*; a surface grows across frames.
- **Primary**: Browser demo 3D pane (`src/surmap/demo/`) — the surface layer is drawn in the 3D
  reconstruction, coloured per surface, toggleable; it replaces the "latest region" layer.
- **Primary**: Demo run history (`src/surmap/demo/history.py`, `demo-history.db`) — surfaces are
  persisted in SQLite per run; scrubbing and reopened runs show surfaces as they were then.
- **Related**: SAM region → dense 3D points (`StreamRegionPoints`, changelog
  `2026-10-31-sam-region-points.md`) — consumed unchanged.

## Summary

A SAM mask's dense points (from the RTAB-Map region query) are no longer a throw-away,
one-frame overlay. The station assigns each point to a *surface* — the 3D shape of one
segmented object — and keeps the surfaces for the whole run. The 3D reconstruction shows the
surface layer, and the surfaces are stored in SQLite with the rest of the run.

## Background

`StreamRegionPoints` answers one polygon on one frame; by contract nothing accumulates. An
object's shape therefore needs a consumer that joins observations across frames. SAM 3.1 track
ids restart every 16-frame propagation window, so they cannot carry identity over a run. Points
already placed by earlier frames can: when a new mask's points land where an earlier surface's
points already are, the mask is the same object seen again.

## Proposed Changes

### What's Changing

- **Assignment by continuation.** Each region's points are voxelised. Match voxels (10 cm) that
  earlier frames assigned to a surface vote for it. The surface holding the largest overlap
  continues if that overlap is ≥ 20 % of the region's match voxels. Otherwise a new surface
  starts. Points on another surface's voxels stay with that surface: a voxel belongs to one
  surface. The newly assigned points join the chosen surface, deduplicated on a 2 cm grid.
- **Moving objects become smeared surfaces.** A surface whose observations drift ≥ 0.4 m from
  where it was first seen is marked moving for good and keeps accumulating — the smear the object
  left. It is drawn red and more opaque than static surfaces.
- **Surface layer in 3D.** The server renders every surface over the RTAB-Map cloud: static
  surfaces translucent in a colour per surface id, moving ones red on top. A *Surfaces* toggle in the 3D pane hides or shows the layer. The browser no
  longer posts region points back to the server (`cloud_regions` is removed).
- **`surface` SSE event** after each `region` event: per region placed, the surface id, label,
  track id, whether it continued an existing surface, the newly assigned points and the
  surface's total.
- **Persistence.** `demo-history.db` gains a `surface_points` table: one row per assignment
  (run, frame, surface, label, track, new points). A snapshot at frame F carries every surface
  accumulated up to F, and its `cloud_png` is rendered with them.

### What's Staying the Same

- `StreamRegionPoints`, `RegionPointSource` and the `region` event: unchanged.
- RTAB-Map's map: surfaces are a separate layer, never written back.
- Runs without a region-capable backend: no `surface` events, nothing persisted.

## Impact Analysis

### Technical Impact

New pure-numpy module `survey/surfaces.py`. The demo wires it between the `region` event and
the history store. One new SQLite table (created `IF NOT EXISTS`; old databases open unchanged).

### User Impact

The 3D pane shows objects building up as SAM keeps segmenting them, and the layer survives
history scrub and reopened runs.

## Implementation Plan

See the changeset's `## Workflow` rows.

## Acceptance Criteria

Listed as the changeset's `## Acceptance Tests` and checked off under its Green row.
