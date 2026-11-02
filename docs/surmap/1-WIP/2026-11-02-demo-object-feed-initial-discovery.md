# Initial Discovery: Demo object feed, car-shaped surfaces, working 3D pane

**Changeset**: [2026-11-02-demo-object-feed.md](./2026-11-02-demo-object-feed.md)
**Date**: 2026-11-02
**Passes**: 1

## Combined Conclusions

- **Smeared surfaces are a data problem, not a drawing one.** `dense_region_points`
  (`src/surmap/slam/dense.py`) keeps every SGBM pixel inside the SAM polygon with
  `0 < z <= max_depth_m` (30 m on KITTI). Mask-edge pixels match the background, and at
  KITTI's fx ≈ 362 px, b = 0.537 m one disparity pixel is metres at 15–30 m. Each region
  therefore carries a tail along the viewing ray. Measured on recorded run `38b8dc54`
  (KITTI 0009, 19 frames, SAM `car`): track 4 at frame 1 has a median range of 5.7 m, a
  p95 of 8.7 m and a maximum of 21.8 m. Accumulated car surfaces are 5–10 m long along
  the view direction.
- **The tails make parked cars "moving".** `SurfaceMap.assign` marks a surface moving
  for good once the region centroid drifts ≥ 0.4 m from the first one. The tails move
  the centroid, so surfaces #3 and #6 (parked cars) turned red.
- **A depth band fixes the shape.** Keeping points within ±1.5 m of the region's median
  range from the camera (a replay with a `SurfaceMap` subclass) gives car surfaces of
  about 1.5 × 1.2 × 2–3.5 m and moving count 3 → 2. The two left are the cars the
  vehicle drives right past: partial views move the centroid, which is the documented
  limit in `surfaces.py`.
- **Near-empty masks start surfaces.** Empty regions already return `None`, but regions
  of 1–35 points (far cars) start surfaces: #1 (4), #2 (2), #7 (5), #12 (35), #15 (17),
  #18 (7), #20 (5), #22 (1). Real car regions have ≥ 260 points after the band.
- **The camera position is not on the region path.** `RegionResult` carries map-frame
  points only. Replays know it (`DenseFrame.to_map`). The live streaming backend knows
  each frame's odometry pose (`frame_odometry(frame_id)`).
- **The 3D pane is dead once a run ends.** `/control` uses `server.current`, which is
  cleared when the run engine finishes, so every `cloud_*` action answers `409 nothing
  is playing`. Probed live on port 8766 after the 19-frame cached rerun finished. The
  page's `postCloud` ignores non-OK responses, so dragging silently does nothing. The PTZ
  pose is also per run (`PlaybackControls`), so a new run resets the view.
- **Even mid-run, PTZ waits for the next map event.** `DemoPlayer` re-renders when
  `cloud_version` changes, but `JournalPlayer` (cached reruns, replays) renders only on
  journalled map events.
- **Drags lose most of their movement.** `postCloudDebounced` keeps only the newest
  `pointermove` delta per 120 ms window (`cloudPending = body`), so a long drag posts a
  few one-event deltas.
- **Seams for the feed.** Surface events (`surface_id`, `label`, `moving`, the newly
  added `points`, `total_points`) stream on every source the page opens. History
  snapshots carry `surfaces` (`surfaces_at`). `page.py` (595 lines) and `server.py`
  (2188) are oversized with open code issues, so the feed script goes in its own module,
  spliced like `CLOUD_SCRIPT`.
- **Tests.** `tests/test_survey_surfaces.py` is fluent (Given/When/Then); demo tests use
  real servers on ephemeral ports (`tests/test_demo_controls.py`). There is no JS test
  harness: page scripts are checked by `node --check`.

## Exploration 1: KITTI surfaces and the 3D pane — 2026-11-02

**Agent**: parent Grep/Read plus replay scripts
**Scope**: why KITTI car surfaces smear and turn red, why the 3D pane does not move

### Sequence

1. Read `README.md` § Dev console: how to run the demo and its flags.
2. Read `src/surmap/survey/surfaces.py`, `src/surmap/survey/mask_cloud.py`: surface assignment.
3. Read `src/surmap/slam/regions.py`, `src/surmap/slam/dense.py`: region points from disparity.
4. Grep `max_depth|SGBM|answerRegion` in `deploy/rtabmap-stream/main.cpp`: sidecar parameters.
5. Read `src/surmap/demo/replay.py` (`JournalPlayer`), grep `src/surmap/demo/history.py`.
6. Ran a scratch replay of run `38b8dc54` printing per-region range percentiles.
7. Ran the same replay with a depth-banded `SurfaceMap` subclass and compared extents.
8. Read `src/surmap/demo/events.py` (`RegionPlacer`, `SurfaceAssigner`).
9. Read `src/surmap/demo/cloud_script.py`; grep `cloud_version|server.current` in `server.py`.
10. `curl POST /control cloud_orbit` against the running console: `409 nothing is playing`.
11. Read `src/surmap/demo/page.py` listeners, `history.py` `snapshot_at` / `surfaces_at`.
12. Read `src/surmap/docs/code-issues/oversized-file-demo-page.md`.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Grep | `cloud_version` | `src/surmap` | `server.py:1265` only in `DemoPlayer` |
| Grep | `server.current = ` | `server.py` | `1482`, `1490`, `1746`, `1932` (cleared on finish) |
| Grep | `PlaybackControls(` | `server.py` | `1030`, `1781`, `1992` |
| Grep | `def frame_odometry` | `slam/streaming.py` | `497` |

### Inspected files

#### `src/surmap/slam/dense.py`

**Why**: how region points get their depth
**Excerpt**:

```python
depth = fx * rig.baseline_m / (disparity[v, u].astype(np.float64) / DISPARITY_SUBPIXELS)
kept = (depth > 0) & (depth <= rig.max_depth_m)
```

#### `src/surmap/survey/surfaces.py`

**Why**: continuation and the moving flag
**Excerpt**:

```python
centroid = points.astype(np.float64).mean(axis=0)
...
drift = float(np.linalg.norm(centroid - shape.first_centroid))
shape.moving = shape.moving or drift >= self._moving_displacement_m
```

#### `src/surmap/demo/server.py` (`/control`)

**Why**: why PTZ does nothing
**Excerpt**:

```python
controls = self.server.current
...
elif controls is None:
    self._send(409, "text/plain", b"nothing is playing")
```

#### `src/surmap/demo/cloud_script.py`

**Why**: drag handling
**Excerpt**:

```js
function postCloudDebounced(body) {{
  cloudPending = body;   // replaces, never adds, the pending delta
  if (cloudPostTimer) return;
```

### Findings

Replay of `38b8dc54`, per region (range from the camera, metres):

| Frame · track | n | p5 / p50 / p95 | max |
|---|---|---|---|
| f1 · t4 | 12414 | 5.2 / 5.7 / 8.7 | 21.8 |
| f1 · t8 | 495 | 14.2 / 18.7 / 21.4 | 29.9 |
| f2 · t4 | 9944 | 4.2 / 4.7 / 9.7 | 30.7 |
| f3 · t9 | 2893 | 9.7 / 10.2 / 13.1 | 30.7 |

Accumulated surfaces (2–98 % extent x, y, z):

| | #3 | #5 | #6 | #9 | #14 | moving |
|---|---|---|---|---|---|---|
| as recorded logic | 3.7 1.1 6.8 | 1.0 1.4 9.9 | 4.2 1.3 7.5 | 1.1 1.3 9.5 | 1.2 1.3 10.4 | 3 |
| ±1.5 m band | 1.7 1.0 3.8 | 0.7 1.3 2.9 | 1.6 1.1 3.4 | 0.9 1.4 2.5 | 1.1 1.3 2.5 | 2 |
