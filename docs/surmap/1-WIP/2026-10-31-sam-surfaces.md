# Changeset: SAM surfaces — region points assigned to persistent object surfaces

**Date**: 2026-10-31
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — new station module + demo wiring + SQLite schema addition across `survey`, `demo`; replaces the `cloud_regions` contract of the 3D pane

## Workflow

- [wf 1] ✅ 2026-10-31 `/plan-red` Plan — PRD, changeset, initial discovery · `PRD-2026-10-31-sam-surfaces.md` + this file + discovery companion
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `code-issues/` — `oversized-file-demo-server.md` ⚠ during (do not grow `server.py`), `oversized-file-demo-page.md` ⚠ during (do not grow `page.py`); todos all `moving-*`, unrelated
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7) — ruff, format, mypy strict green; pytest 679 passed / 12 skipped
- [wf 2] ✅ 2026-10-31 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 2 new suites red at collection (`surmap.survey.surfaces` / `SURFACE_COLOURS` missing) + 1 rewritten page test red; rest green — committed with the changeset
  - [x] Acceptance tests written and failing for the right reason
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ✅ 2026-10-31 `/green` Green — implement until every red test passes · gates green: 700 passed / 12 skipped; `server.py` 1819 → 1814 (moving smears added on the developer's request)
  - [x] `survey/surfaces.py`: `SurfaceMap.assign` (continuation by match-voxel overlap, one owner per voxel, 2 cm dedup), `Surface`, `SurfaceAssignment`
  - [x] `demo/events.py`: `SurfaceAssigner` turns a `region` event into a `surface` event
  - [x] `demo/history.py`: `surface_points` table, `record_surface`, `surfaces_at`, `snapshot_at` carries `surfaces`
  - [x] `demo/server.py`: `_Display` yields `surface` after `region`; the player renders the surface layer (re-render on change); `/control` `cloud_surfaces` toggle replaces `cloud_regions`; `_stream` records `surface` events; snapshot `cloud_png` drawn with surfaces — net growth ≤ 0 lines
  - [x] `demo/cloud_script.py`: Surfaces toggle; `setRegionLayer` / `listenForRegions` removed
  - [x] Every acceptance test below passes
  - [x] Moving surfaces (developer request): `SurfaceMap` marks a surface moving once its region centroid drifts ≥ 0.4 m from its first observation (sticky; the smear keeps accumulating); `moving` in the `surface` event, `surface_points.moving`, `surfaces_at`
  - [x] `demo/surface_render.py`: static surfaces translucent (α 0.5) in their colour; moving surfaces red (α 0.9) drawn on top
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/architecture.md` §6 `SemanticMap` / §10 — the surface layer (station-assigned, per run, persisted) beside region points
  - [ ] `README.md` §Demo — the Surfaces layer and toggle
  - [ ] Changelog entry `docs/surmap/changelog/2026-10-31-sam-surfaces.md`
  - [ ] `src/surmap/docs/code-issues/oversized-file-demo-server.md` / `…-page.md` — measurement history row for this PR
  - [ ] PRD, changeset and discovery companion deleted from `1-WIP/`
  - [ ] (optional) Production readiness — run if a real SAM run shows `surface_points` growth per run that needs a cap

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-31-sam-surfaces-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Prerequisites

### Code Issues

| Record | Class | Effect on this change | Outcome |
|---|---|---|---|
| `src/surmap/docs/code-issues/oversized-file-demo-server.md` (1819 lines, Restructure: required) | ⚠ during | New logic lives in `survey/surfaces.py`, `demo/events.py`, `demo/history.py`; the `cloud_regions` path it replaces is deleted, so `server.py` does not grow. The split itself stays its own restructure | ➖ unchanged — 1819 → 1814, measurement row added, record stays open |
| `src/surmap/docs/code-issues/oversized-file-demo-page.md` (523 lines) | ⚠ during | The toggle is added from `cloud_script.py`; `page.py` is not touched | ➖ unchanged — `page.py` not touched (523) |

## Affected Packages

- **surmap**: `survey/surfaces.py` (new), `demo/events.py`, `demo/history.py`, `demo/server.py`,
  `demo/cloud_script.py`
- **tests**: `tests/test_survey_surfaces.py` (new), `tests/test_demo_surfaces.py` (new),
  `tests/test_demo.py`, `tests/test_demo_regions.py`, `tests/test_demo_history.py`

## Related Feature Documentation

- [PRD](./PRD-2026-10-31-sam-surfaces.md)

## Summary

The station assigns each dense region point to a persistent object surface (continuation by
overlap with points earlier frames assigned), the 3D pane draws the surface layer, and the
surfaces are stored per run in `demo-history.db`.

## Background

See the PRD. Region points are per frame by contract; SAM 3.1 ids restart every 16 frames; the
developer chose continuation by overlap with already-assigned points as the identity rule.

## Scope

- **Implementation**: surface assignment, demo `surface` event, server-owned surface layer and
  toggle, SQLite persistence and snapshot replay
- **Testing**: unit tests for `SurfaceMap`, store tests, demo acceptance tests
- **Documentation**: architecture, README, changelog at wrap
- **Out of scope**: motion classification of surfaces; meshing; restoring a `SurfaceMap` into a
  new run; the `server.py` split

## Technical Changes

### State A (Current)

- `RegionPlacer.region_event` → `region` SSE event per `sam` event (per mask: `track_id`,
  `label`, `status`, `points`).
- The 3D layer was meant to be the browser POSTing `cloud_regions` back; `listenForRegions` is
  defined in `cloud_script.py` but never called, so no region reaches the view today.
  `render_cloud_view(regions=…)` colours by `track_id % 4`; `PlaybackControls` keeps the latest
  set only.
- `RunHistoryStore`: `runs`, `frames`, `maps`, `detections`; no regions.

### State B (Target)

- `surmap.survey.surfaces.SurfaceMap(voxel_m=0.02, match_voxel_m=0.10, min_overlap=0.2)`:
  - `assign(frame_id, track_id, label, points) -> SurfaceAssignment | None` (None for no points);
  - the region's match voxels owned by surfaces vote; the most-voted surface continues if its
    votes ≥ `min_overlap` × the region's match voxels, else a new surface (ids from 1);
  - points in match voxels owned by *another* surface are not assigned; unowned match voxels
    become the chosen surface's; points are deduplicated per 2 cm voxel within a surface;
  - `surfaces() -> tuple[Surface, ...]` (id, label = the first label, points), `version` bumps
    on every assignment.
- `surface` SSE event (after each `region` event that placed points): `{"frame_id", "surfaces":
  [{"surface_id", "label", "track_id", "continued", "points", "total_points"}]}`.
- 3D pane: `render_cloud_view(surfaces=((surface_id, points), …))` in
  `SURFACE_COLOURS[surface_id % n]`; drawn by the player from its `SurfaceMap`; a change in the
  surface layer triggers a re-render like a pose change. `/control` `{"action":
  "cloud_surfaces", "visible": bool}` shows/hides it; `cloud_regions` is gone (400).
- `RunHistoryStore.record_surface(run_id, *, frame_id, surface_id, label, track_id, points)`;
  `surfaces_at(run_id, frame_id)` → `[{"surface_id", "label", "points"}]` accumulated over
  rows with `frame_id ≤` the given one; `snapshot_at` adds `"surfaces"`; the snapshot handler
  renders them into `cloud_png`.

### Delta (What's Changing)

#### surmap

- **New** `survey/surfaces.py`.
- `demo/events.py`: `SurfaceAssigner` (wraps a `SurfaceMap`, region event → surface event).
- `demo/history.py`: table + two methods + snapshot field.
- `demo/server.py`: `REGION_COLOURS` → `SURFACE_COLOURS`, `regions=` → `surfaces=`;
  `PlaybackControls` `cloud_regions`/`set_cloud_regions` → `surfaces_visible`/`set_surfaces_visible`;
  `_Display` owns the `SurfaceAssigner`; recording and snapshot rendering.
- `demo/cloud_script.py`: toggle button; region forwarder removed.

## Verification

**Method:** V1-fail→pass — acceptance tests below, red before, green after.
**Command:** `uv run pytest -q tests/test_survey_surfaces.py tests/test_demo_surfaces.py tests/test_demo_history.py tests/test_demo.py tests/test_demo_regions.py`
**Before:** red — `surmap.survey.surfaces` missing; no `surface` event; no `surface_points` table.
**After:** all green, plus the full gate set.

**Recorded (Green, 2026-10-31):** the command above green; full gates green (ruff, format, mypy
strict, pytest 695 passed / 12 skipped). Rendered page JS passes `node --check`. Live run on the
real streaming sidecar (`scripts/demo.py --dataset euroc-v1-01-easy --sam-fake --frames 120`):
120 `region` → 119 `surface` events (the last region arrives after the sidecar closed, as in
#55), 118/119 continuations of surface 1, new points per frame 4127 → ~500 as voxels fill,
30 817 points total, 119 `surface_points` rows; the final `cloud_png` shows surface 1 in
`SURFACE_COLOURS[1]` over the RTAB-Map cloud. The fake SAM's centred box is not a real object,
so its single chained surface is expected; real SAM 3.1 objects on the GPU are not verified here.

**Recorded (moving smears, 2026-10-31):** gates green, 700 passed / 12 skipped. Same EuRoC run:
surface 1 stays static (drift < 0.4 m), drawn translucent over the cloud. KITTI drive 0009,
60 frames, fake SAM: 60 separate static surfaces, no continuation — the red smear is proven by
`test_an_object_driving_past_becomes_a_red_smeared_surface_in_the_3d_pane` and the render
tests, not by a live moving object.

## Acceptance Tests

### surmap — `SurfaceMap` (`tests/test_survey_surfaces.py`)

- the first region starts surface 1 with its points, one per 2 cm voxel
- a region overlapping an earlier surface continues it, even under a new SAM track id
- a continued surface gains only the points in voxels it did not hold
- a region that overlaps nothing starts a new surface
- a region below the overlap threshold starts a new surface
- points on another surface's voxels stay with that surface
- a region with no points assigns nothing

### surmap — demo (`tests/test_demo_surfaces.py`)

- every region event is followed by a surface event for the same frame
- the same object on the next frame continues its surface
- surfaces are persisted per run and survive reopening the database
- a snapshot carries the surfaces accumulated up to its frame
- the cloud view draws surfaces in the surface colour; hidden surfaces are not drawn
- `/control` `cloud_surfaces` toggles the layer and bumps the cloud version; `cloud_regions` is rejected

## Decisions & Trade-offs

- **Identity = continuation by overlap** (developer's choice), not SAM track id; label is not a
  match criterion (a surface keeps its first label).
- **Two grids**: 10 cm match voxels tolerate SGBM noise and viewpoint change between frames;
  2 cm storage voxels keep the shape detailed without unbounded growth.
- **Moving objects are shown as smears, by the developer's choice.** A surface whose region
  centroid drifts ≥ `moving_displacement_m` (0.4 m) from its first observation is marked moving
  for good; its points keep accumulating and are drawn red and more opaque (α 0.9) than static
  surfaces (α 0.5), so the smear reads as motion. This departs from architecture §3.3/§6
  (moving objects as snapshots, never accumulated) for the display layer only — nothing is fused
  into RTAB-Map's static scene; the wrap updates architecture §6 to say so.
- **Known limit: motion needs continuation.** An object moving more than its own overlap per
  frame (fast, or far with sparse stereo) never continues a surface, so it leaves one static
  surface per frame instead of one red smear. Seen live on KITTI with the fake SAM (60 frames →
  60 surfaces, none continued). Using SAM's track id within its 16-frame window as a
  continuation hint would close it; not done here.
- **Existing tests of the replaced contract are rewritten**, not deleted: the `REGION_COLOURS`
  render test and the `cloud_regions` controls test become their surface equivalents; the page
  test asserts the toggle instead of `setRegionLayer`.
