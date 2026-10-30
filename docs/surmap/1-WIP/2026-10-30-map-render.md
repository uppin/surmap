# Changeset: Recognisable live floor plan and map-frame camera

**Date**: 2026-10-30
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: changes
**Complexity**: 3 — sidecar odom field, server-side raster, page drawing

## Workflow

- [wf 1] ✅ 2026-10-30 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
  - [x] Record initial discovery (accuracy, divergence, calibration probes)
  - [x] Create changeset
- [wf 2] ✅ 2026-10-30 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 8 red
  - [x] Protocol: odom carries its map-corrected pose
  - [x] Floor plan: a point lands at its extent pixel in its grey; denser areas more opaque; identical input → identical image
  - [x] Extent: corners map to the padded canvas; it only grows
  - [x] Camera: placed by its map-corrected pose
  - [x] Run the new tests (verify they fail for missing implementation)
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Sidecar emits `map_pose` = `getMapCorrection() · odomPose`
  - [ ] `FloorExtent`, `render_floor_plan`; map and final events send the image + extent
  - [ ] Page draws the image, then trajectory and camera through the same extent
  - [ ] Rebuild the sidecar; real-container e2e asserts map poses arrive
  - [ ] Real check on sbs_01
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] Changelog entry `docs/surmap/changelog/2026-10-30-map-render.md`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-30-map-render-initial-discovery.md).

## Stack Context

Stacked on `feat/ntu-viral-demo` (changeset `2026-10-30-ntu-viral-demo.md`).

## Affected Packages

- **surmap**: `slam/stream_protocol.py`, `demo/server.py`, `demo/page.py`
- **deploy**: `deploy/rtabmap-stream/main.cpp`

## Summary

The live floor plan becomes one image of every map point — stable
between updates, walls as solid lines — and the camera marker sits on
its trajectory after loop closures.

## Technical Changes

### State A (Current)

- Map events send a 4,000-point stride sample (`cloud_xy`); the page
  draws dots and recomputes the extent client-side.
- The camera marker uses raw odometry (up to 5.3 m off the graph).

### State B (Target)

- `OdomUpdate.map_pose` (optional): the sidecar sends
  `getMapCorrection() · odomPose`; the camera uses it when present.
- `FloorExtent(min_x, max_x, min_z, max_z)` with `to_pixels` on a
  340 px canvas (10 px padding, uniform scale); the player keeps a
  grow-only extent over cloud, trajectory and camera.
- `render_floor_plan(xz, grey, extent)` → base64 RGBA PNG: per pixel the
  mean grey of its points, alpha rising with point count (log scale).
- Map and final events send `floor_png`, `extent` and `trajectory_xy`
  (no `cloud_xy`); the batch path renders its z-up cloud the same way.
- Page: draws `floor_png`, then trajectory and camera via the extent.

## Verification

**Method:** V1 fail→pass and a real check on sbs_01.
**Command:** `uv run pytest -q tests/test_demo_floor_plan.py tests/test_demo.py tests/test_slam_stream_protocol.py`
**Before:** 8 new tests fail.
**After:** tests green; full gates green; real check recorded at wrap.

## Decisions & Trade-offs

- **Server-side raster over sending points (user decision).** All ~1M
  points in, ~340×340 PNG out; deterministic, so nothing shimmers.
- **3D view not now (user decision).**
- **SLAM accuracy unchanged here.** Measured limit of stereo-only
  odometry on sbs_01 (ATE ≈ 3.3 m, scale 1.2); IMU fusion is separate.
