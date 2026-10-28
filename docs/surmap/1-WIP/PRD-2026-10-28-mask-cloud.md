# Project SAM masks onto the cloud - PRD

**Date**: 2026-10-28
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Base-station mask fusion (`docs/architecture.md` §4.2 `surmap_fuse`, §5, §6 `PointCloud`) — a SAM polygon can now claim camera-frame cloud points and return them in the map frame. The ROS2 node itself stays design intent.

## Summary

Mask pixels become map-frame points. A SAM polygon selects the cloud
points that project inside it. A supplied RTAB-Map pose carries those
points into the map frame. No new model.

## Background

Architecture §6 says the point-to-pixel link is what lets a 2D SAM mask
claim 3D points, and §5 names fuse as masks × cloud × pose. The station
already emits mask polygons and the survey already emits camera-frame
points, but nothing intersects them. On-board object points stay
box-based and coarse; this is the registration step that uses the mask
boundary instead. Follow-up task 5 on PR #28.

## Proposed Changes

### What's Changing

- `points_in_mask(points, rig, polygon, width, height, pose=None)` keeps
  camera-frame points whose pinhole projection lies inside the polygon
  and inside the frame, dropping `z <= 0.05`.
- When `pose` is passed, each kept point is transformed with
  `surmap.geometry.to_map_frame`.
- An empty polygon returns an empty tuple.
- The result is registration only. Points are not written into RTAB-Map.

### What's Staying the Same

- SAM detection, the ONNX session, and mask outline extraction.
- On-board box lifting in `CoralObjectPointSource`.
- RTAB-Map's internal map. Object points stay a layer on its output.
- No network and no new model dependency.

## Impact Analysis

### Technical Impact

- New module `src/surmap/survey/mask_cloud.py`. Pure function, numpy-free.
- Callers pass an existing `StereoRig`, a `SamDetection.mask_polygon`,
  the frame size, and an optional `Pose`.
- No server route, proto, or dependency change.

### User Impact

- No operator-facing workflow change in this change. A later demo can
  call the function. This PR does not wire one.

## Implementation Plan

1. Failing acceptance tests for the square-mask pose case and the empty polygon.
2. Implement the minimum projection, depth gate, frame gate, and pose transform.
3. Record the behaviour in `docs/architecture.md` at wrap. Do not edit `README.md`.

## Acceptance Criteria

- Three camera-frame points and a square polygon return only the inside point, translated by a known pose.
- An empty polygon returns an empty tuple.
- Points with `z <= 0.05` are dropped.
- No network. Ruff and mypy strict pass.

## References

### Affected Features (Complete List)

- Base-station mask fusion — `docs/architecture.md` §4.2, §5, §6

### Related Documentation

- Task: https://github.com/uppin/surmap/pull/28#issuecomment-6479199252
- Scope guardrail: `AGENTS.md` (passive survey; no write-back into RTAB-Map)
