# GPS-anchored semantic map snapshot - PRD

**Date**: 2026-10-28
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: semantic map export — no feature document exists yet. Wrap creates `docs/semantic-map-snapshot.md` with the JSON schema.
- **Related design**: `docs/architecture.md` §6 (layered `SemanticMap`), §7 (ENU origin and recorded GPS offset), §12 (GeoJSON still an open decision). This PRD does not edit that file.

## Summary

One UTF-8 JSON file is the semantic-map export until the GeoJSON decision in architecture §12 is settled. Each landmark keeps a stable id, map-frame position, geodetic position or null, label, description, model id, and motion. Moving tracks are a separate list. An optional mask-point cloud can be attached per landmark so a later mask projection can ride along without a schema change.

## Background

Follow-up task 6 on PR #28 asks for the first real caller of `GpsCheckpoint`: associate each landmark with the nearest fix by timestamp, record the offset, and take the first fix as the origin. A later map question-answering feature and a 3D viewer will read this file. Task 5 produces map-frame points from a SAM mask on another branch; those points need a place on the landmark.

## Proposed Changes

### What's Changing

- A snapshot can be built from object tracks and GPS checkpoints, written as UTF-8 JSON, and read back equal to what was written.
- Static tracks become landmarks. A track whose centroid moves past `classify_motion`'s threshold appears only under `dynamic`.
- With no fix, the origin is absent and lat/lon/alt are null.
- Every landmark has a stable `id` (the decimal track id) and an optional `mask_points` list of map-frame xyz.

### What's Staying the Same

- GeoJSON is not adopted. Architecture §12 stays an open decision.
- Object points are not written into RTAB-Map. Moving objects are not fused into the static layer.
- `classify_motion`'s threshold and return values do not change.
- `README.md` is not edited.

## Impact Analysis

### Technical Impact

- New module `src/surmap/map/snapshot.py`. Stdlib `json` only. No network.
- Tests in `tests/test_map_snapshot.py`.
- Consumers that do not exist yet (map Q&A, 3D viewer, the task 7 demo) will depend on the schema in `docs/semantic-map-snapshot.md`.

### User Impact

- A survey session can be handed off as one JSON file with GPS coordinates where a fix exists, and with moving objects kept out of the static landmarks.

### Business Impact

- Unblocks the hackathon demo's snapshot write (task 7) and any viewer that needs a stable landmark id.

## Implementation Approach

- Call `classify_motion`. Do not trust `ObjectTrack3D.motion`.
- Origin is the earliest checkpoint by `t_ns`. Map xyz is local ENU metres from that fix: x east, y north, z up. Lat/lon/alt use a documented constant metres-per-degree conversion from that origin.
- Nearest checkpoint by absolute `t_ns` difference supplies `offset_ns = landmark_t_ns - checkpoint_t_ns`. Ties go to the earlier fix.
- `mask_points` is null when the caller did not attach a cloud, and a list when it did (including an empty list).

## Acceptance Criteria

- Two checkpoints, one static track, and one track whose centroid moves past the `classify_motion` threshold produce JSON whose static landmark has a non-zero `offset_ns`, and whose moving track appears only under `dynamic`.
- Reading a written snapshot equals the snapshot that was written.
- No network. Ruff, mypy strict, and pytest pass.

## Dependencies

- Existing `surmap.types.GpsCheckpoint`, `ObjectTrack3D`, and `surmap.motion.classify_motion`.
- No dependency on the mask-projection branch. `mask_points` is an input the caller may omit.

## Timeline

- Single change: failing tests, then the module, then the schema doc. No calendar estimate.
