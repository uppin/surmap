# Changeset: Project SAM masks onto the cloud

**Date**: 2026-10-28
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — one package, two owned symbols (`points_in_mask`, polygon containment), unit tests only

## Workflow

- [wf 1] ✅ 2026-10-28 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + changeset + discovery
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Square mask returns only the inside point, translated by a known pose
  - [ ] Empty polygon returns an empty tuple
  - [ ] Points with `z <= 0.05` are dropped
  - [ ] A projection outside the frame is not a mask pixel
  - [ ] Without a pose, a kept point stays in the camera frame
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/architecture.md` — State B mask-registration paragraph
  - [ ] `docs/surmap/changelog/2026-10-28-mask-cloud.md`
  - [ ] `src/surmap/docs/changesets/2026-10-28-mask-cloud.md`
  - [ ] Test quality and fluent readability validated
  - [ ] (optional) Production readiness validated (3) — run if the diff reaches server code

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-28-mask-cloud-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: [docs/architecture.md](../../architecture.md) — name the registration function under the fuse data flow
  - [changelog](../changelog/) — one history entry at wrap
  - [src/surmap/docs/changesets](../../../src/surmap/docs/changesets/) — one package history entry at wrap

## Summary

Add `points_in_mask` so a SAM polygon selects camera-frame cloud points
and, when a pose is passed, returns them in the map frame.

## Background

Follow-up task 5 on PR #28. Architecture already describes fuse as
masks × cloud × RTAB-Map pose, and the point-to-pixel link as the way a
mask claims 3D points. The pieces exist separately: polygons on
`SamDetection`, camera points from stereo, `to_map_frame` for the pose.
Nothing intersects a polygon with a cloud. On-board lifting uses a box,
which includes background at the edges. This step uses the mask outline
and does not write the result into RTAB-Map.

## Scope

- `src/surmap/survey/mask_cloud.py` — `points_in_mask`
- `tests/test_mask_cloud.py` — the acceptance cases below
- Stable docs at wrap: architecture paragraph, product changelog, package changeset history
- No README edit, no new dependency, no model, no network, no server route

## Technical Changes

### State A (Current)

- `SamDetection.mask_polygon` is a pixel outline. Nothing consumes it for 3D.
- `CoralObjectPointSource` keeps stereo points whose projection falls in a tracked box, drops `z <= 0.05`, and maps them with `to_map_frame`.
- `project_overlay` drops the same near points and rejects projections outside `[0, width) × [0, height)`.
- `surmap_fuse` in `docs/architecture.md` is design intent. There is no `mask_cloud` module.
- Object points are layered onto RTAB-Map output and are never written back.

### State B (Target)

- `points_in_mask(points, rig, polygon, width, height, pose=None) -> tuple[Vec3, ...]`
  projects each camera-frame point with the rig (`u = fx * x / z + cx`, `v = fy * y / z + cy`).
- A point is kept only when `z > 0.05`, the projection lies inside the frame, and the projection lies inside the polygon (even-odd, ring closed from the last vertex to the first).
- An empty polygon, or any polygon with fewer than three vertices, returns `()`.
- When `pose` is not `None`, each kept point is `to_map_frame(point, pose)`. Otherwise the camera-frame point is returned.
- Order of kept points matches the input order.
- The function takes no SLAM backend and writes nothing.

### Delta (What's Changing)

#### surmap

- **API**: new `surmap.survey.mask_cloud.points_in_mask`.
- **Implementation**: pinhole projection, frame gate, even-odd polygon test, optional pose transform.
- **Dependencies**: none.

## Verification

**Method:** V1, fail→pass — `tests/test_mask_cloud.py` acceptance tests
**Command:** `uv run pytest -q tests/test_mask_cloud.py`
**Before:** (recorded on the red commit)
**After:** (recorded when green)

## Testing Plan

### Testing Strategy

**Primary Test Approach:**

- **Test Level**: Unit
- **Why**: One pure function. No hardware, network, model, or server.
- **Approach**: Build a rig, a square, and three camera points → call `points_in_mask` → assert the map-frame tuple.

### Testing Options Analysis

#### Option 1: Unit tests through `points_in_mask`

**Test Level**: Unit
**Description**: The public function is the specification. Containment, the depth gate, the frame gate, and the pose are observed only through its return value.

**Scope**: The acceptance cases in the task, plus the frame gate and the no-pose case the signature implies.
**Why Chosen**: Nothing below the function is a separate behaviour worth its own test.

## Acceptance Tests

- Three points and a square polygon return only the inside point, translated by a known pose (`z <= 0.05` included among the three so the depth gate is part of that result).
- An empty polygon returns `()`.
- A point that projects outside `[0, width) × [0, height)` is dropped even when the polygon would contain that pixel.
- With `pose=None`, the inside point is returned unchanged in the camera frame.
