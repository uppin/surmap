# CM5 incremental point emitter — PRD

**Date**: 2026-10-27
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Board API (docs/architecture.md §10) — the CM5
  point-streaming behaviour its clients will observe.

## Summary

A pure, per-stream emitter that forwards only newly spawned points:
a point already sent at the same position for the same designation is
never resent. RTAB-Map points use designation 1; object points are
grouped per object designation.

## Proposed Changes

### What's Changing

- `IncrementalPointEmitter` in `surmap.survey.points`: `emit(designation,
  points)` returns only points not yet sent for that designation in this
  stream; `reset()` clears the seen-set (new stream / calibration change).
- Exact `Vec3` equality, per designation — the same coordinates under a
  different designation are a different point.

### What's Staying the Same

- Producers (`SlamBackend`, object reconstruction) still return full
  per-frame points; dedup lives only in the emitter.

## Acceptance Criteria

- [ ] First emission forwards all points; identical re-emission forwards none.
- [ ] A moved point (new position) is forwarded; per-designation sets are independent.
- [ ] `reset()` makes previously seen points forwardable again.
