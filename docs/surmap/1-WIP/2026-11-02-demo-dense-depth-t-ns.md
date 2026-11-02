# Changeset: Demo dense depth is RTAB-Map's, per frame

**Date**: 2026-11-02
**Status**: ✅ Wrapped
**Type**: Bug Fix
**Behaviour**: changes
**Complexity**: 2 — one package; the server's dense-depth route, the page's request, a per-pixel read of the journalled disparity; HTTP-level and unit tests

## Workflow

- [wf 1] ✅ 2026-11-02 `/plan-red` Plan — changeset, initial discovery · this file + companion (re-planned: RTAB-Map is the frame-level source of truth)
  - [x] Record initial discovery
  - [x] Create changeset
- [wf 2] ✅ 2026-11-02 `/plan-red` Red — reproduction test, committed · `test_slam_dense.py` red (no `display_depth`); `test_demo_dense_depth.py` 4 red (404 on `/runs/<id>/dense-depth`, page asserts); committed with the fix, not separately
  - [x] Reproduction tests written and failing for the right reason
- [wf 3] ✅ 2026-11-02 `/green` Green — fix until the reproduction passes · gates green: pytest 1340 passed, 7 skipped; streaming e2e 11 passed (real container)
  - [x] `slam/dense.display_depth` — journalled disparity per display pixel, region geometry
  - [x] `GET /runs/<id>/dense-depth?frame_id=` from the run's (root's) dense buffer; old `/dense-depth` removed
  - [x] Page asks by run and frame id, says when RTAB-Map has none, retries on the frame's region
  - [x] `StereoReconstructor.depth_map` removed (its only user was the old route)
  - [x] Page draws a frame together with its overlay (no flashing); misses cached per run + frame
  - [x] Sidecar SGBM pads the reference's left `numDisparities` columns, so the disparity reaches the frame edge
  - [x] Rebuild RTAB-Map: `/stream?rebuild_rtabmap=<run_id>` + page button, SAM answered from the run's journal (`demo/sam_journal.py`)
- [wf 4] ✅ 2026-11-02 `/pr-wrap` Wrap — validate, clean up, verification, docs · changelog entry, code-issue rows, 1-WIP removed
  - [x] Verification executed — result recorded
  - [x] README.md § Dev console — Video toggles and Rebuild RTAB-Map bullets
  - [x] docs/surmap/changelog/2026-11-02-demo-dense-depth-rtabmap.md — history entry
  - [x] src/surmap/docs/code-issues/oversized-file-demo-{server,page}.md — measurement rows

## Initial Discovery

Full exploration: [initial-discovery.md](./2026-11-02-demo-dense-depth-t-ns-initial-discovery.md).

## Affected Packages

- `deploy/rtabmap-stream/main.cpp` (`fullFrameDisparity` padding; new image tag).
- `surmap`: `slam/dense.py` (`display_depth`), `demo/history.py` (`dense_frame`),
  `demo/server.py` (route), `demo/page.py` (request), `demo/dense_view.py` (doc),
  `survey/stereo.py` (`depth_map` removed).

## Summary

The video's Dense depth overlay shows RTAB-Map's own dense stereo for the frame — the SGBM
disparity the sidecar journalled — instead of a separate NumPy match of the display pair.

## Technical Changes

### State A (Current)

`GET /dense-depth?dataset=&t_ns=` matched the display pair with the NumPy block matcher at
1/3 width. Against the sidecar's SGBM on KITTI its median depth error was 40–85 % (60–92 % of
pixels > 30 % off), and it disagreed with the SAM pane, which draws SGBM. The page also sent a
rounded `t_ns` (JSON double), so 429/447 KITTI and all EuRoC frames were 404.

### State B (Target)

- `display_depth(rig, frame, size)` reads the journalled disparity for every display pixel:
  pixel centre → raw pixel → rectified pixel (`undistort_points`, `lround`), `z = fx·b/d` up
  to the rig's cap — the same geometry the region answers use.
- `GET /runs/<run_id>/dense-depth?frame_id=<n>` serves it as the overlay PNG, from the
  run's root recording (a replay reads its recording's buffer). No journalled frame, rig or
  run → 404. Nothing is matched in its place.
- The page requests by `currentRunId` + `frame_id` (an exact small integer), says "No
  RTAB-Map dense depth for this frame (only SAM frames have it)" on a 404, and retries when
  that frame's `region` event arrives (live dense is journalled with the region).

### Delta

Overlay source NumPy → RTAB-Map's journal; route moved under `/runs/<id>/`; key `t_ns` →
`frame_id`.

## Verification

**Method:** V1 fail→pass, plus V3 on the KITTI console
**Command:** `uv run pytest -q tests/test_demo_dense_depth.py tests/test_slam_dense.py`
**Before:** `display_depth` missing; `/runs/<id>/dense-depth` 404; page still asks
`/dense-depth?…&t_ns=`.
**After:** all pass; `tests/test_slam_streaming_dense_e2e.py` edge-band tests red → green on the rebuilt
image (left band 0 % → matched like the middle). New sidecar on KITTI frames 185–200: columns
0–127 of frame 200 matched 86 % (was 0 %), rest 93 %; a left-edge region 3100 points. KITTI run `acdcc6aa` (447 frames): 427 frames have RTAB-Map dense depth,
20 have none (no SAM frame) and say so. Rebuilt `acdcc6aa`'s RTAB-Map on the new sidecar → run `4f0e962f`
(447 frames, 447 recorded SAM results, SAM not run): left 128 columns 0 % → 82 % matched
(rest 90 %), and it is the scene's cached run; frame 120 overlay checked by eye. Frame 200 overlay checked by eye: road near → far,
buildings far, left SGBM band empty.

## Decisions & Trade-offs

- **No fallback.** A frame without RTAB-Map's dense buffer shows none, rather than a second
  matcher's answer that disagrees with the map.
- **By `frame_id`, not `t_ns`.** The journal is keyed by frame; an integer that small
  survives JSON, so the `t_ns` precision bug goes away instead of being worked around.
- **Pixel-centre scaling.** Identical to the region path at the rig's size (KITTI's display
  is); one pixel row better at the edge when the display is larger.
- **Pad, don't shrink the search.** The frame's widest disparity is 34 px of the 128 searched;
  a smaller search would cut the near range (fB/128 ≈ 1.5 m). Padding keeps it and the LR check
  rejects matches into the padding.
- **Hold the frame for its overlay.** Drawing frame and overlay together trades a ~20–50 ms
  display delay for no flashing; a frame RTAB-Map has none for is drawn plain at once.
- **Old journals keep the band.** Runs recorded before the image change have the empty left
  band in their dense buffer; only new recordings get the full width.
- **Out of scope:** the mission demo's `DenseStereoFallback` still uses the NumPy matcher.
