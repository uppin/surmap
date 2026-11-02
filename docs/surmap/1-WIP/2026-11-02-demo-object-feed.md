# Changeset: Demo object feed, car-shaped surfaces, working 3D pane

**Date**: 2026-11-02
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — one package; demo server integration tests; a session-level PTZ state shared across run threads (concurrency); the `RegionResult` and `region` event shape gain fields; a camera reprojection with distortion

## Workflow

- [wf 1] ✅ 2026-11-02 `/plan-red` Plan — PRD, changeset, initial discovery · PRD-2026-11-02-demo-object-feed.md + 2026-11-02-demo-object-feed.md; baseline 1166 passed / 28 skipped
  - [x] Record initial discovery
  - [x] Cross-check src/surmap/docs/todo/ and src/surmap/docs/code-issues/
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7)
- [wf 2] ✅ 2026-11-02 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 5 suites red @ `14c6bf4` (4 import errors, 1 assertion)
  - [x] Acceptance tests written and failing for the right reason
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ✅ 2026-11-02 `/green` Green — implement until every red test passes · 1203 passed / 28 skipped; ruff, format, mypy strict green
  - [x] Milestone 1: `SurfaceMap` depth band and minimum points
  - [x] Milestone 2: the camera pose reaches `SurfaceMap` (`RegionResult.camera`, `region` event `viewpoint`, live backend from the dense line)
  - [x] Milestone 3: session-level `CloudViewer`; every `cloud_*` action works without a run and answers with `cloud_png`
  - [x] Milestone 4: page — drags send their whole movement; the response image is shown
  - [x] Milestone 5: object feed module (`demo/object_feed.py`) spliced into the page
  - [x] Milestone 6: region pixels (`project_to_display`), `region` event `pixels`, SAM pane depth-gradient overlay
  - [x] Acceptance: `tests/test_survey_surfaces.py`, `tests/test_demo_object_feed.py`, `tests/test_demo_cloud_ptz.py` pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] README.md § Dev console — object feed bullet; PTZ works after a run
  - [ ] docs/architecture.md §6 SAM surface layer — depth band and minimum points
  - [ ] docs/surmap/changelog/2026-11-02-demo-object-feed.md — history entry
  - [ ] src/surmap/docs/code-issues/oversized-file-demo-page.md and oversized-file-demo-server.md — measurement rows
  - [ ] Validate tests (`/validate-tests`)

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-02-demo-object-feed-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Prerequisites

### Deferred TODOs

- — unrelated: `src/surmap/docs/todo/` holds GPS-on-wire and moving-object EuRoC items, outside this path.

### Code Issues

- ⚠ during: `oversized-file-demo-page.md` (page.py 595 lines) — the feed script goes in its own module, so `page.py` gains only the splice line and markup.
- ⚠ during: `oversized-file-demo-server.md` (server.py 2188 lines) — the PTZ state moves into a new `demo/cloud_view.py`, so `server.py` must not grow.

## Affected Packages

- `surmap` — `survey/surfaces.py`, `slam/regions.py`, `slam/dense.py`, `slam/streaming.py`, `demo/events.py`, `demo/server.py`, `demo/cloud_script.py`, `demo/page.py`, new `demo/cloud_view.py`, new `demo/object_feed.py`

## Related Feature Documentation

- PRD: [PRD-2026-11-02-demo-object-feed.md](./PRD-2026-11-02-demo-object-feed.md)
- README.md § Dev console, docs/architecture.md §6

## Summary

Surfaces keep only a region's points near its median range from the camera, and need 50
points to start or continue. The demo gets a per-surface object feed with client-side 3D
previews, and the SAM pane draws each object's dense points coloured by depth. The main 3D pane's PTZ moves to the session and works with or without a run.

## Background

See the PRD. The user's report, on KITTI 0009: car surfaces "spanning far beyond what
each standing car would produce", masks with no depth "shouldn't become surfaces yet",
and the 3D pane "I can't move by moving mouse or trackpad".

## Scope

In: the four items of the PRD's *What's Changing*. Out: rewriting surfaces recorded in
old runs' history; the partial-view centroid drift of cars driven past; the
sidecar's SGBM settings.

## Technical Changes

### State A (Current)

- `SurfaceMap.assign(frame_id, track_id, label, points)` takes every point of the region.
  An empty region returns `None`. Any other region starts or continues a surface.
- `RegionResult` has no camera pose. The `region` event carries
  `track_id, label, status, points` per region. The SAM pane draws mask outlines and labels only.
- `PlaybackControls` (one per run engine) holds the PTZ pose and surface visibility.
  `/control` uses `server.current`, which is `None` once the run ends, and answers 409.
  `JournalPlayer` re-renders only on journalled map events.
- `cloud_script.py` keeps only the newest drag delta per 120 ms.
- The page has no per-object view.

### State B (Target)

- `SurfaceMap(depth_band_m=1.5, min_points=50)`. `assign(..., viewpoint=None)`:
  1. With a viewpoint, the region keeps points whose range from it is within
     `depth_band_m` of the median range.
  2. Fewer than `min_points` left returns `None`, and the region neither starts nor
     continues a surface.
- `RegionResult.camera: Pose | None` is the camera-to-map pose of the answering channel's
  rectified camera:
  - `dense_region_points` sets it from `frame.to_map` (offset by the baseline on channel 1).
  - The live streaming backend remembers each dense line's `to_map`. The sidecar writes
    that line before its region answer, so the pose is known by the time the answer is
    released.
- `surfaces.object_points(points, viewpoint, band_m)` is the band, a pure function that
  `SurfaceMap` and `RegionPlacer` share.
- `dense.project_to_display(points, camera, rig, channel, size)` maps map-frame points to
  display pixels: into the rectified camera, rotated back by Rᵀ, distorted with K and D
  (OpenCV's forward model), then scaled to the display size.
- `RegionPlacer` writes into each region of the `region` event:
  - `viewpoint`, the camera position;
  - `pixels`, `[u, v, range_m]` of the banded points, sampled to ≤ 1500, when the source
    knows its `region_rig`.
  `SurfaceAssigner` passes the viewpoint on.
- SAM pane: draws each region's `pixels` over its mask, coloured near → far over that
  region's range, and appends the range to the label.
- `demo/cloud_view.py`: `CloudViewer`, owned by the server, holds the pose, surface
  visibility, version and the last drawn scene. `render(points, colors, bounds, layer)`
  draws under the current pose and remembers the scene, and `rerender()` draws the
  remembered one again. Every run's `PlaybackControls` uses the server's viewer.
  `/control` `cloud_*` works without a run and returns the pose plus `cloud_png`.
- `cloud_script.py`:
  - Drag and wheel deltas add up while a post is pending.
  - A `cloud_png` in a PTZ response replaces the image.
  - Wheel with `ctrlKey` (trackpad pinch) zooms.
- `demo/object_feed.py` (`OBJECT_FEED_SCRIPT`, `OBJECT_FEED_MARKUP`):
  - **Cards.** One card per surface id: label, `#id`, points, static or moving, frames
    seen, and a canvas with its own orbit camera (drag, Shift+drag, wheel or pinch,
    buttons). The preview is centred on the surface and coloured by height, red when
    moving.
  - **Sources.** It is fed by `surface` events on every stream and rebuilt from
    `snap.surfaces` when a moment is scrubbed. It is cleared on a new `run` event.

### Delta (What's Changing)

#### surmap

| File | Change |
|---|---|
| `survey/surfaces.py` | `depth_band_m`, `min_points`, `viewpoint` |
| `slam/regions.py` | `RegionResult.camera` |
| `slam/dense.py` | sets `camera`; `project_to_display` |
| `slam/streaming.py` | sets `camera` from the dense line |
| `demo/events.py` | `viewpoint` and `pixels` on regions; viewpoint to surfaces |
| `demo/cloud_view.py` | new: `CloudViewer` |
| `demo/server.py` | uses the viewer; `/control` without a run |
| `demo/cloud_script.py` | accumulated deltas, response image, pinch |
| `demo/object_feed.py` | new: feed script and markup |
| `demo/page.py` | splices the feed; SAM pane draws region pixels |

## Verification

**Method:** V1 fail→pass for the Python behaviour; V4 for the browser interaction (no JS test harness in this repo)
**Command:** `uv run pytest -q tests/test_survey_surfaces.py tests/test_slam_dense.py tests/test_demo_object_feed.py tests/test_demo_cloud_ptz.py`
**Before:** the new tests fail: no `depth_band_m` / `min_points` / `viewpoint`, `/control` answers 409 after the run, no feed on the page
**After:** all pass; full gates green

V4, in the in-app browser on KITTI 0009 (cached rerun of `38b8dc54`, then a Replay):
1. Let the run finish, drag and pinch the 3D pane: the view follows the movement.
2. The SAM pane shows depth-coloured dense points on each car mask, with no background tail.
3. The feed lists car surfaces with car-sized previews; each card orbits independently.
4. Scrub the timeline: the feed follows the moment.

**Approved:** pending — the user asked for the change in this session; V4 is the only way to exercise pointer input without a JS harness.

## Validation Results

### Verification run — 2026-11-02

- **V1:** the five suites in **Command** went from red @ `14c6bf4` to green. Full suite:
  1203 passed / 28 skipped. The JS helpers and the PTZ readout are exercised in node.
- **Existing tests changed:**
  - `test_demo_regions.py`: two region-dict equalities gain `viewpoint: None, pixels: []`.
    The fake backend's points are now a settable `points`.
  - `test_demo_surfaces.py`: the fake car is a 24 × 3 patch (72 points) instead of 2
    points, because a 2-point region is now "no depth yet".
    `test_the_page_toggles_the_surface_layer…` expects `cloud_surfaces` with nothing
    playing to answer 200 (was 409): the view is the session's.
  - My own red tests had two arithmetic errors, corrected to exact geometry: the
    default azimuth is −0.8, not 0, and the square's nearest range is √(2² + 0.4²).
- **Headless replay of `38b8dc54` through the new server:**
  - Surfaces went from 42 to 28, the smallest from 1 point to 275, and moving from 3 to 2.
  - Car surfaces are about 1.5 × 1.1 × 2.5–3.8 m.
  - Region pixels: 94–98 % of each region's pixels lie inside its own mask.
  - `cloud_orbit` after the run answers 200 with `cloud_png`.
- **V4, in the in-app browser:**
  - **Feed:** 28 cards (2 moving).
  - **3D pane drag:** a real 200 px CDP mouse drag on the finished run turned the
    3D pane from az −46° to +46°, the whole drag.
  - **Pinch:** a ctrl+wheel pinch zoomed it to 0.55×.
  - **Feed preview:** a feed card's preview orbited.
  - **SAM pane:** draws depth-coloured points per car (for example `6.1–7.3 m`).
  - **Scrub:** rebuilds the feed from the recorded surfaces.
  - **Console:** no page errors.
- **Flaky, unrelated:** `test_moving_differencing.py::test_differencing_is_within_frame_budget`
  (a 200 ms wall-clock budget) failed 1 of 4 full runs while the console and browser
  loaded the machine. It passed 5 of 5 alone, and `src/surmap/moving` is untouched since
  `b2de4bf`. Not proven on an untouched checkout.
- **Observed, out of scope:** near-left KITTI cars get points only on their rear. The
  sidecar's SGBM (`numDisparities` 128 at 620 px) cannot match the image's leftmost 128
  columns. That is also why some masks get no depth.

## Acceptance Tests

### surmap

- `tests/test_survey_surfaces.py`: a tail along the view ray is cut; a sparse region starts nothing and continues nothing; a later dense one starts the surface; without a viewpoint only the minimum applies.
- `tests/test_slam_dense.py`: a dense region's result carries the camera pose (channel 0, channel 1); `project_to_display` returns the pixel a point was back-projected from (no distortion, and with distortion round-tripping `undistort_points`).
- `tests/test_slam_streaming_dense.py`: a live region answer carries the pose of the dense line before it.
- `tests/test_demo_object_feed.py` (regions): a `region` event carries `viewpoint` and banded `pixels` with ranges, capped at 1500.
- `tests/test_demo_object_feed.py`: the region event carries the viewpoint and the surface is banded; the page carries the feed and feeds it from surface events and snapshots.
- `tests/test_demo_cloud_ptz.py`: `cloud_orbit` after the run answers 200 with a re-rendered `cloud_png`; the pose carries into the next run; the drag handler accumulates deltas.

## Decisions & Trade-offs

- **One PR for both** the surface fix and the feed, at the user's request. This is a
  Feature changeset: the surface changes are new parameters with new defaults, and the
  PTZ fixes are in the same pane.
- **Feed previews render client-side; the main pane stays server-rendered.** User choice:
  independent PTZ per card with no round trip. Per-object clouds are small (a few hundred
  to about 35k points, capped at 4000 per card by sampling).
- **Band at the surface layer, not in the sidecar.** Live and replay stay identical,
  and replays of existing recordings show the fix without a rebuild.
- **±1.5 m and 50 points** come from the measured KITTI replay (discovery). They are
  constructor parameters, like `min_overlap`.
- **The 50-point minimum is for dense regions only** (decided during Green).
  `SurfaceMap`'s default stays 1, because mission objects (`surmap.mission.objects`) assign
  sparse snapshot hits with no viewpoint, and 50 broke 12 mission tests and real mission
  tracking. The demo's `SurfaceAssigner` uses `DENSE_REGION_MIN_POINTS` (50). The band
  only applies with a viewpoint, so mission is unchanged.
- **`render_cloud_view` and `CloudPose` moved to `demo/cloud_view.py`**, re-exported from
  `server.py`, which shrank from 2188 to 2051 lines.
- **A pre-existing page bug fixed in scope.** `surfacesButton` was a `const` inside the
  `if (cloudCanvas)` block, so `postCloud` threw a swallowed `ReferenceError` after every
  answer: the pose readout and the Hide/Show surfaces label never updated (on `main` too).
  Found in the V4 run; reproduction `test_a_ptz_answer_updates_the_readout_and_the_surfaces_button`.
- **SAM-pane points come from the region event, not the surface.** They are the
  region's banded points on that frame, so they match the mask. Snapshots don't
  journal region pixels, so a scrubbed moment shows masks only.
- **The depth gradient is per object.** Near → far over each object's own range shows
  its shape. One global scale would paint a whole car the same colour.
- **The PTZ pose is per session, not per viewer.** The console already has one run
  shared by all viewers.
