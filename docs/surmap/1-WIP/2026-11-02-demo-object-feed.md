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
- [wf 3] ✅ 2026-11-02 `/green` Green — implement until every red test passes · 1249 passed / 28 skipped; ruff, format, mypy strict green
  - [x] Milestone 1: `SurfaceMap` depth band and minimum points
  - [x] Milestone 2: the camera pose reaches `SurfaceMap` (`RegionResult.camera`, `region` event `viewpoint`, live backend from the dense line)
  - [x] Milestone 3: session-level `CloudViewer`; every `cloud_*` action works without a run and answers with `cloud_png`
  - [x] Milestone 4: page — drags send their whole movement; the response image is shown
  - [x] Milestone 5: object feed module (`demo/object_feed.py`) spliced into the page
  - [x] Milestone 6: region pixels (`project_to_display`), `region` event `pixels`, SAM pane depth-gradient overlay
  - [x] Milestone 7: hover picking — `cloud_ids_png` beside every `cloud_png`; hover shows the surface id and selects all its pixels; clicking it scrolls the feed to its card and highlights it (and hovering a card selects it in the pane)
  - [x] Acceptance: `tests/test_demo_cloud_pick.py` passes
  - [x] Milestone 8: SAM pane in the same selection — hovering a mask selects its surface (3D points light up), clicking it opens the feed card; hovering a surface in 3D (or its card) outlines its masks on the SAM frame shown
  - [x] Acceptance: `tests/test_demo_sam_pick.py` passes
  - [x] Milestone 9: Follow (checked by default) — a chase view behind and above the camera along its heading, the camera at 3/4 image height with a camera marker; the un-mirrored projection
  - [x] Acceptance: `tests/test_demo_cloud_follow.py` passes
  - [x] Milestone 10: SAM view object cards — one non-overlapping card per object (id, depth range) with a leader to it, filled circles at both ends; hovering a card selects its object, clicking opens the feed
  - [x] Acceptance: `tests/test_demo_sam_cards.py` passes
  - [x] Milestone 10b: each card as close to its own object as it fits — beside its mask box, not in rows at the top; leaders from the card's nearest edge
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

- **Hover picking (milestone 7):**
  - Every rendered cloud comes with `cloud_ids_png` (`CloudViewer.render_view`): same
    size and projection, each surface pixel holding its id as R + 256·G with alpha 255,
    and transparent elsewhere. Hidden surfaces give an empty id image, and a moving
    surface drawn over a static one owns the shared pixels, as in the visible image.
  - It rides with every `cloud_png`: map and final events, replays, the `/control`
    answer and snapshots. It is render-only, so it is never journalled.
  - The page decodes it. Hover picks the nearest surface pixel within 4 px
    (`surfaceIdNear`), shows `label #id · points` in a tooltip, tints every pixel of
    that surface (`selectionMask`). A click on it (press and release within 4 px, so a
    drag is still an orbit) scrolls the feed to its card and highlights it
    (`focusFeedItem`). Hovering a card selects its surface in the pane.

- **SAM pane picking (milestone 8):**
  - **Mapping.** The page keeps, per frame, which surface each SAM track was assigned to
    (`noteSurfaces`, from `surface` events).
  - **Hover and click.** Hovering a mask (`maskAt`: the smallest polygon containing the
    cursor) selects that surface: its 3D points light up and its card is the hovered
    one. A click on it scrolls the feed to that card.
  - **Shared selection.** The selection is one value (`cloudSelected`), so hovering a
    surface in 3D or its card outlines the surface's masks on the shown SAM frame in
    yellow.
  - **Limit.** A scrubbed moment has no surface events, so its masks don't link.

- **Follow (milestone 9):**
  - **Session state.** `CloudViewer.follow` is on by default.
  - **The camera in the scene.** A rendered scene carries the camera it was drawn for:
    the shown frame's floor camera (`x, z, dx, dz`). It comes from the live player, the
    replay's frame events or the snapshot's `camera`.
  - **Following.** The view looks along the camera's heading from behind it, at the
    pane's tilt. The orbit target sits ahead of the camera, so the camera lands at 3/4
    of the image height at any tilt and zoom. The view spans 24 m at zoom 1.
  - **Marker.** A yellow arrow marks the camera.
  - **PTZ while following.** Tilt and zoom keep following. Orbit and pan leave Follow,
    starting from the exact follow view.
  - **Toggle.** `/control` `cloud_follow` sets it, and every answer says `follow`.
  - **Page.** A "Follow" checkbox in the 3D pane's header, checked by default, synced
    from each answer.
  - **Mirror fix.** The projection was mirrored (`(x, −y, z)` is left-handed). Image u
    is now negated, so the camera's right is drawn on the right.

- **SAM view object cards (milestone 10):**
  - **Cards.** Each SAM object gets a card, colour-coded:
    - **cyan** `label #surface` once its object is a surface;
    - **grey** `label #track` (SAM's track id) while it has too few depth points to be
      in 3D;
    - **yellow** when selected.

    It shows its depth range when it has any, and a legend under the SAM view says what
    the colours mean. (Milestone 10b replaced a `label · SAM track` text tag.) Masks keep their outline; the loose text
    labels are gone.
  - **Layout.** Each card goes to the nearest free spot next to its own object's mask box
    (`layoutCards`):
    - the nearest spot that overlaps no other card and stays on the image;
    - not over the object itself while a spot beside it is free;
    - centred just above the box first, then below, left and right, then the nearest
      free point further out;
    - smallest objects first, since they have the fewest free spots near them.

    (Milestone 10b: the first layout packed cards in rows at the top of the image, far
    from their objects.)
  - **Leaders.** A leader runs from the card's nearest edge point to the object's
    centroid, with a filled circle at each end.
  - **Selection.** Hovering a card selects its object, like hovering its mask, and a
    click opens the feed. The selected object's card is drawn in yellow.

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
| `demo/sam_depth.py` | track → surface per frame; SAM hover, click and highlight |
| `demo/page.py` | splices the feed; SAM pane draws region pixels; passes `cloud_ids_png` |
| `demo/surface_render.py` | `surface_pixels` shared by the colour and id images |
| `demo/replay.py`, `demo/history.py` | id image rides with replays; render-only |

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
- **Milestone 7 (picking):**
  - **Tests:** 15 new tests, red @ the milestone-7 test commit, now green. The fake
    renderer in `test_demo_replay_sam.py` now returns `{cloud_png, cloud_ids_png}`,
    because `CloudRenderer` returns the named images.
  - **V4, real CDP mouse events on the finished KITTI run:**
    - **Hover:** hovering car #27 shows `car #27 · 336 pts · static — click to open in
      the feed`, selects all 112 of its pixels and sets a pointer cursor. Hovering
      alone does not navigate.
    - **Click:** a click highlights card #27 and scrolls it into the feed's view.
    - **Drag:** a 60 px drag from the same point does not navigate.
    - **Card hover:** hovering card #2 selects surface 2 in the pane.
  - **Found in the V4 run:** nested smooth `scrollIntoView` did not scroll the feed in
    the webview. The feed's `scrollTop` is now set from the card's offset. The tooltip
    also flips left at the pane's right edge.
- **Milestone 8 (SAM view in the selection):**
  - **Tests:** 6 new tests, red @ `307860b`, now green.
  - **V4, real CDP mouse events:**
    - **SAM hover:** hovering car track 8's mask on frame 13, which became surface 27,
      lights all 112 of surface 27's pixels in 3D and outlines the mask. Its title reads
      `car #27 — click to open in the feed`.
    - **SAM click:** clicking the mask brings card #27 into view in the feed.
    - **3D hover:** hovering surface 27 in 3D outlines track 8 on the SAM frame.
    - **Leave:** leaving clears both views.
    - **Console:** no page errors.
- **Milestone 9 (Follow):**
  - **Tests:** 14 new tests, red @ `ecef12b`, now green.
  - **Existing tests changed:**
    - `test_demo_replay_sam.py`'s fake renderer takes the camera.
    - `test_demo_regions.py`'s `FakeRegionBackend` passes `odometry` through.
    - `test_demo_cloud_pick.py::test_the_id_image_holds_each_surfaces_id…` views from
      azimuth π. Its "7 left of 9" held only because the image was mirrored: the
      default azimuth −0.8 looks toward +x/−z, where +x truly runs left.
  - **V4 on KITTI 0009:**
    - **Opening:** the page opens with Follow checked. The camera arrow sits low and
      centred, pointing up the road, and parked cars on the camera's left are drawn
      left of it.
    - **Replay:** during a 1× replay the framed camera advanced from z = 4.5 to
      20.2 m with heading +z.
    - **Take-over:** a real 200 px drag unchecked Follow and continued from the follow
      azimuth (180° + 92° = 271°), with no jump.
    - **Re-check:** re-checking resumed following.
    - **Console:** no page errors.
- **Milestone 10 (SAM object cards):**
  - **Tests:** 8 new tests, red @ `746ad52`, now green.
  - **Test fix:** the card test labels the shared stub objects `car`, because SAM's
    objects always carry a label.
  - **V4 on KITTI frame 13:**
    - **Layout:** 13 cards, 0 overlaps, 0 off the image.
    - **Content:** linked cards read `car #27 / 5.1–7.1 m` and `car #28 / 11.8–14.3 m`;
      the others read `car · SAM n`.
    - **Hover:** hovering car #27's card selected surface 27; the card, its leader and
      track 8's mask turned yellow.
    - **Click:** opened card #27 in the feed.
    - **Console:** no page errors.
  - **Seen, then fixed in 10b:** with 13 objects the row layout filled the top two rows
    of the image, and leaders from far cars crossed.
- **Milestone 10b (cards next to their objects, colour-coded):**
  - **Tests:** 4 layout tests rewritten for the new requirement (red @ `0ba61a1`), plus
    a colour and legend test. Two earlier assertions were replaced: "rows at the top"
    and "leader from the bottom edge".
  - **V4 on KITTI frame 13:**
    - **Layout:** 13 cards, 0 overlaps. 9 of 13 sit within 4 px of their own mask box;
      the farthest is 34 px away.
    - **Leaders:** 7–64 px, against 30–100+ px in rows.
    - **Colours:** cyan `car #27` and `car #28`, the rest grey, with the legend shown.
    - **Console:** no page errors.
  - **Found while testing:** a careless replacement had deleted the SAM selection block
    (`samSelectedTracks`, `drawSamSelection`, the canvas listeners). The
    `test_demo_sam_pick.py` tests caught it, and it was restored from `HEAD`.
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
- `tests/test_demo_sam_cards.py`: `layoutCards` never overlaps or leaves the image and centres a card over its object when there is room; `cardAt`; the SAM script's cards name the surface (or SAM track) with the depth range and select on hover; masks draw no loose labels.
- `tests/test_demo_cloud_follow.py`: probe surfaces at, ahead of and right of the camera land where a chase view puts them (two headings); tilt and zoom keep the camera at 3/4 height; the marker; follow by default and off on orbit and pan without a jump; `cloud_follow` and `follow` in answers; players and snapshots draw for their camera; the page's checkbox.
- `tests/test_demo_sam_pick.py`: `polygonContains` and `maskAt` in node; the SAM script maps a hovered mask to its frame's surface, outlines the selected surface's masks, and is wired to hover, click and the shared selection.
- `tests/test_demo_cloud_pick.py`: the id image holds each surface's id on its pixels, nothing on map-only pixels or hidden surfaces, the moving surface on shared pixels; map events, replays, `/control` answers and snapshots carry it; `surfaceIdNear` and `selectionMask` in node; the page wires hover to the tooltip and the selection, and a click (`isClick`) to `focusFeedItem`.
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
- **Feed navigation is on click, not hover** (the user's follow-up). Hover only names
  and selects, so moving across the pane never scrolls the feed under the reader.
- **Picking uses a server-rendered id image**, so the page needs no geometry and the
  pick matches exactly what is drawn, including occlusion by a moving surface.
- **Follow frames on the floor camera** (`x, z, dx, dz`), which frames already carry,
  so recordings replay with Follow and nothing new is journalled. The view's height is
  the map's mid-height, not the camera's, because frames don't journal it.
- **The mirror fix changes every 3D render.** It is what makes left and right right in
  the chase view. The default free view (azimuth −0.8) now shows the scene the right
  way round, so it looks flipped next to before.
- **The PTZ pose is per session, not per viewer.** The console already has one run
  shared by all viewers.
