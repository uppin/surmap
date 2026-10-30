# Changeset: Camera indicator on the live floor plan

**Date**: 2026-10-30
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — one frame-event field from existing odometry, page drawing

## Workflow

- [wf 1] ✅ 2026-10-30 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
  - [x] Record initial discovery
  - [x] Create changeset
- [wf 2] ✅ 2026-10-30 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 3 red
  - [x] Demo: a live frame carries its camera's floor-plan position, heading and field of view
  - [x] Demo: a frame without odometry, or playback without SLAM, carries no camera
  - [x] Run the new tests (verify they fail for missing implementation)
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Frame events carry `camera` from the shown frame's odometry pose
  - [ ] Page: floor plan redrawn per frame with the camera dot and field-of-view wedge
  - [ ] Real check in the browser
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] `README.md` §Demo — camera indicator
  - [ ] Changelog entry `docs/surmap/changelog/2026-10-30-map-camera-indicator.md`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-30-map-camera-indicator-initial-discovery.md).

## Stack Context

Stacked on `feat/demo-controls` (changeset `2026-10-30-demo-controls.md`).

## Affected Packages

- **surmap**: `demo/server.py`, `demo/page.py`

## Summary

The live floor plan marks the virtual camera — position, heading and
field of view — for the frame on screen, so the viewer sees where the
drone is and what it looks at.

## Technical Changes

### State A (Current)

- The floor plan shows the cloud and the trajectory line only.

### State B (Target)

- Frame events carry `camera`: `{"x", "z", "dx", "dz", "fov_deg"}` — the
  shown frame's odometry position on the floor plane, its forward axis
  projected there (unit length), and the display's horizontal field of
  view `2·atan(width / 2 / fx)`; `null` without that frame's odometry or
  without SLAM.
- The page keeps the latest map data and redraws the floor plan with
  each frame: a dot at the camera and a translucent wedge of its field
  of view along its heading.

## Verification

**Method:** V1 fail→pass and a browser check.
**Command:** `uv run pytest -q tests/test_demo.py`
**Before:** 3 new tests fail (`KeyError: 'camera'`).
**After:** tests green; full gates green; browser check recorded at wrap.

## Decisions & Trade-offs

- **Pose of the shown frame, not the newest odometry.** Riding on the
  frame event keeps the marker in sync with the video (frames are held
  until their odometry lands); it uses odometry, not the optimized graph,
  so after a loop closure it can sit slightly off the re-drawn trajectory
  until the next map event.
