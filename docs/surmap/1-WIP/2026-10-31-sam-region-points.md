# Changeset: SAM region → dense 3D points (`StreamRegionPoints`)

**Date**: 2026-10-31
**Status**: ✅ Complete
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — proto contract change + native sidecar protocol v4 + cross-thread request/response in the streaming backend + CM5 backend mode + demo, across `deploy`, `slam`, `survey`, `demo`

## Workflow

- [wf 1] ✅ 2026-10-31 `/plan-red` Plan — PRD, changeset, initial discovery · `PRD-2026-10-31-sam-region-points.md` + this file + discovery companion
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `code-issues/` (nothing in path; no `code-issues/` dir)
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7) — ruff, format, mypy strict green; pytest 636 passed / 3 skipped
- [wf 2] ✅ 2026-10-31 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 6 new files red at collection (`surmap.slam.regions` / `encode_region` missing) + 3 proto tests red; 634 existing green
  - [x] Acceptance tests written and failing for the right reason
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ✅ 2026-10-31 `/green` Green — implement until every red test passes · gates green: 680 passed / 3 skipped with `SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1`; region e2e green on the real sidecar
  - [x] Proto: `RegionQuery`, `RegionPoints`, `RegionStatus`, `rpc StreamRegionPoints`; bindings regenerated (`scripts/gen_survey_rpc.py`)
  - [x] `surmap.slam.regions`: `RegionQuery`, `RegionResult`, `RegionStatus`, `RegionPointSource` port, `InMemoryRegionPointSource`, `invalid_reason()`
  - [x] Stream protocol v4: `encode_region`, `region` line → `RegionResult`, hello `region_buffer_s`
  - [x] `StreamingRtabmapBackend.region_points()` — non-dropping request path through the writer, reply matched by `query_id`, timeout → `SidecarError`
  - [x] Sidecar: ring of rectified pairs + odom pose bounded by `region_buffer_s`; polygon raw→rectified (`cv::undistortPoints` with K, D, R, P of the channel); SGBM disparity referenced to the requested channel over the polygon's bbox rows; back-project; `getMapCorrection() * odomPose` (+ baseline for channel 1); depth-capped by `max_depth_m`
  - [x] CM5: `stream_region_points` handler mounted on `Cm5SurveyService`; chunks of ≤ 10 000 points, `final` on the last; no source → stream rejected
  - [x] CM5: `--slam-backend streaming` builds `StreamingRtabmapBackend` as both `SlamBackend` and `RegionPointSource`
  - [x] Demo: `LiveSlamBackend.region_points`; each released `sam` event → `region` event (per object: track id, label, status, points); 3D pane draws the latest region layer, replacing the previous one
  - [x] Demo: `--sam-fake` (launcher + `build_server(sam_fake=True)`) runs `InMemoryVideoSamDetector` with a fixed centred polygon
  - [x] Real-container e2e green (dense > sparse, inside-polygon reprojection, channel 0 ≈ channel 1)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/connectrpc.md` / `README.md` — the new rpc and `--slam-backend streaming`
  - [ ] `docs/architecture.md` — region points as a read-only layer on RTAB-Map's output
  - [ ] `README.md` §Demo — `--sam-fake` and the region layer
  - [ ] Changelog entry `docs/surmap/changelog/2026-10-31-sam-region-points.md`
  - [ ] PRD, changeset and discovery companion deleted from `1-WIP/`
  - [ ] (optional) Production readiness — run if the sidecar ring's memory at CM5 resolution is not yet measured

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-31-sam-region-points-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: `slam/regions.py` (new), `slam/stream_protocol.py`, `slam/streaming.py`,
  `survey/cm5_server.py`, `survey/cm5_main.py`, `survey/v1/survey_pb2.py(i)` (generated),
  `demo/server.py`, `demo/page.py`, `demo/cloud_script.py`
- **proto**: `proto/surmap/survey/v1/survey.proto`
- **deploy**: `deploy/rtabmap-stream/main.cpp`
- **scripts**: `scripts/demo.py` (`--sam-fake`)

## Related Feature Documentation

- [PRD](./PRD-2026-10-31-sam-region-points.md)

## Summary

Adds `Cm5SurveyService.StreamRegionPoints`: a BIDI stream where each query names a frame,
the channel SAM segmented, and a polygon; each answer is every point dense stereo recovers
inside that polygon on that one frame, in the map frame. The RTAB-Map sidecar computes it
from a short ring of rectified pairs; the CM5 gains a live RTAB-Map mode to serve it; the
demo draws each SAM mask's region on the 3D pane.

## Background

See the PRD. In short: RTAB-Map's own 2D→3D link is sparse and left-only, and the keyframe
cloud is downsampled and keyframe-only. A SAM mask needs per-pixel depth on the exact frame
and channel it was drawn on.

## Scope

- **Contract**: new rpc and messages in `surmap.survey.v1`
- **Native**: sidecar protocol v4 with region requests and a frame ring
- **Implementation**: region port + in-memory adapter, streaming backend request path, CM5
  handler and live mode, demo region layer and fake SAM
- **Testing**: acceptance + unit tests below; real-container e2e
- **Documentation**: connectrpc, architecture, README, changelog at wrap

## Technical Changes

### State A (Current)

- `Cm5SurveyService` has `StreamSurvey`, `StreamDetections`, `StreamMovingAreas`. No way to
  ask for 3D points of an image region.
- Sidecar protocol v3: `hello`, `pair` in; `ready`, `odom` (pose, `map_pose`, inlier
  keypoints), `keyframe` (5 cm-voxel camera-frame cloud), `graph`, `error` out. Rectified
  pairs are discarded after each frame.
- `StreamingRtabmapBackend` has one writer thread fed by a bounded drop-oldest pair queue.
- `cm5_main --slam-backend {inmemory,sidecar}`; `sidecar` is the batch backend (no live pose).
- Demo `sam` events carry channel-0 mask polygons in display pixels; nothing turns them
  into 3D.

### State B (Target)

**Contract** (`survey.proto`):

```proto
enum RegionStatus {
  REGION_STATUS_UNSPECIFIED = 0;
  REGION_STATUS_OK = 1;
  REGION_STATUS_FRAME_EXPIRED = 2;   // not (or no longer) in the CM5's frame ring
  REGION_STATUS_NO_POSE = 3;         // tracking was lost on that frame
  REGION_STATUS_INVALID_QUERY = 4;   // channel not 0/1, < 3 vertices, zero image size
}
message RegionQuery {
  int64 query_id = 1;   // assigned by the requester; every response repeats it
  int64 frame_id = 2;   // as sent on StreamSurvey
  int32 channel = 3;    // 0 (left) or 1 (right): the image the polygon was drawn on
  uint32 width = 4;     // size of that image, pixels (the polygon's coordinate space)
  uint32 height = 5;
  repeated Point2 polygon = 6;
}
message RegionPoints {
  int64 query_id = 1;
  int64 frame_id = 2;
  int32 channel = 3;
  RegionStatus status = 4;
  repeated Point3 points = 5;  // map frame; this frame only, never accumulated
  bool final = 6;              // last message for this query_id
}
service Cm5SurveyService { ... rpc StreamRegionPoints(stream RegionQuery) returns (stream RegionPoints); }
```

**Python port** (`surmap.slam.regions`): `RegionQuery`, `RegionResult(query_id, frame_id,
channel, status, points)`, `RegionStatus` enum, `RegionPointSource.region_points(query,
timeout=5.0) -> RegionResult`, `InMemoryRegionPointSource(points_by_frame)` (unknown frame →
`FRAME_EXPIRED`, records queries), `invalid_reason(query) -> str | None`.

**Sidecar protocol v4**: hello gains `region_buffer_s` (default 10). Request
`{"type":"region","query_id","frame_id","channel","width","height","polygon":[[x,y],…]}`
(framed, no payload). Response line `{"type":"region","query_id","frame_id","channel",
"status":"ok|expired|no_pose|invalid","points":[[x,y,z],…]}` (map frame).

**Sidecar region algorithm**: ring of `{frameId, tNs, leftRect, rightRect, odomPose|lost}`,
evicted by `tNs` age against the newest frame. Polygon scaled from `(width,height)` to the
configured size, then raw→rectified via `cv::undistortPoints(pts, K, D, R, P)` of the
requested channel; `cv::fillPoly` mask; SGBM disparity with the requested channel as
reference (channel 1: both images flipped horizontally and swapped), computed over the
polygon's bounding rows only; every masked pixel with valid disparity back-projected with
the rectified model (channel 1 shifted by `+baseline` along x), depth-capped by
`max_depth_m`, transformed by `getMapCorrection() * odomPose`. No downsampling.

**CM5**: `stream_region_points(requests, source, max_points_per_message=10_000)`; invalid
queries answered `INVALID_QUERY` without calling the source; source calls run in a worker
thread. `--slam-backend streaming` (+ `--calibration-dir`) wires `StreamingRtabmapBackend`.

**Demo**: `region` SSE event `{frame_id, regions: [{track_id, label, status, points}]}`,
points capped at 50 000 per event for the browser (count reported); the 3D pane keeps only
the latest region layer.

### Delta (What's Changing)

#### surmap
- **API**: new rpc + messages; new port module; `StreamingRtabmapBackend.region_points`;
  `cm5_main --slam-backend streaming`; demo `--sam-fake`, `region` event
- **Implementation**: control-request path in the streaming backend writer; reply table
  keyed by `query_id` in the reader

#### deploy
- **Implementation**: frame ring, region handler, protocol version 4

### Architecture Diagram

None declared for the survey services; `docs/architecture.md` gets a prose note at wrap.

## Verification

**Method:** V1 fail→pass — acceptance tests below; plus the real-container e2e (skips
locally without the derived image, required in CI).
**Command:** `uv run pytest -q tests/test_slam_regions.py tests/test_slam_stream_protocol_regions.py tests/test_slam_streaming_regions.py tests/test_survey_region_points.py tests/test_survey_proto.py tests/test_demo_regions.py tests/test_slam_streaming_regions_e2e.py`
**Before:** recorded at Red — the six new files fail at collection with
`ModuleNotFoundError: surmap.slam.regions` (and `encode_region` missing); the three proto
tests fail on the missing `StreamRegionPoints` / `RegionQuery`; every existing test green
(634 passed / 3 skipped with the new files collected-but-erroring; see Validation Results).
**After:** all green; full gates green; e2e numbers (points per query, dense/sparse ratio,
channel 0↔1 median distance, region latency) recorded at wrap.

## Testing Plan

| Tier | File | What |
|---|---|---|
| Contract | `tests/test_survey_proto.py` | rpc present and BIDI; query/response fields |
| Unit | `tests/test_slam_regions.py` | `invalid_reason`, in-memory source |
| Unit | `tests/test_slam_stream_protocol_regions.py` | `encode_region` frame; `region` line decode per status; v4; hello `region_buffer_s` |
| Integration (fake process) | `tests/test_slam_streaming_regions.py` | `region_points` round trip; replies matched by `query_id` out of order; timeout; not dropped behind stalled pairs |
| Acceptance (in-process rpc) | `tests/test_survey_region_points.py` | statuses, chunking + `final`, no cross-query mixing, rejection without a source, mounted on the service |
| Acceptance (demo) | `tests/test_demo_regions.py` | fake SAM → `sam` then `region` events; page draws and replaces the region layer; CLI `--sam-fake` |
| E2E (real container) | `tests/test_slam_streaming_regions_e2e.py` | dense ≫ sparse; reprojection inside polygon; channel 0 ≈ channel 1; expired frame |

## Acceptance Tests

New files reuse the existing suites' helpers (`tests.test_slam_streaming`,
`tests.test_slam_stream_protocol`, `tests.test_slam_streaming_e2e`, `tests.test_demo`) so a
missing module during red does not stop those suites from collecting.

- `tests/test_survey_region_points.py` — a tracked frame answers with every point in its
  region · the channel SAM segmented is passed to the source and repeated · a large region
  is chunked and only the last chunk is final · each query is answered from its own frame,
  never accumulated · a frame the CM5 no longer holds is reported expired · an invalid
  query is refused without asking for depth (no such channel / two vertices / no image
  size) · a CM5 without a region source rejects the stream · the region stream is mounted
  on the CM5 survey service
- `tests/test_demo_regions.py` — every SAM result is followed by its region's points · a
  region event carries each mask's map-frame points · regions are asked on the left
  channel at the display size · a region that could not be placed keeps its reason and no
  points · without a live map SAM results get no region · the fake SAM drives regions onto
  the 3D pane · the demo CLI offers a fake SAM
- `tests/test_slam_streaming_regions_e2e.py` — a SAM region is answered with dense points
  on both channels (dense > 2 000 and > 20× sparse; ≥ 95 % reproject inside the polygon;
  channel-1 median nearest-neighbour distance to the channel-0 surface < 5 cm; frame 1
  expired with a 2 s ring)
- `tests/test_survey_proto.py` — the CM5 service lists `StreamRegionPoints` (contract
  edit) · a region query names frame, channel, image size and polygon · region points
  carry status, map points and the last-chunk flag

Lower tier: `tests/test_slam_regions.py` (validation, in-memory adapter),
`tests/test_slam_stream_protocol_regions.py` (v4, hello ring length, region
encode/decode per status), `tests/test_slam_streaming_regions.py` (round trip,
out-of-order answers, timeout by name, region written ahead of queued pairs, hello).

## Decisions & Trade-offs

- **Dense stereo in the C++ sidecar, not the Python reconstructor** — developer's choice:
  true rectification and SGBM; the Python path has neither.
- **Depth referenced to the requested channel** — developer's choice ("dense, both
  channels"); RTAB-Map has no channel-1 2D→3D link.
- **Time-bounded ring, explicit `FRAME_EXPIRED`** — developer's choice; no fallback to
  JPEG-compressed keyframe images.
- **CM5 switches to the live sidecar in this PR** — developer's choice; batch mode stays
  available.
- **Demo polygons from a fake SAM** — developer's choice (`--sam-fake`); real SAM 3.1
  (#54) feeds the same path when `--sam-device` is given.
- **Pose = current map correction × the frame's odom pose**, read when the query is
  answered: the best current estimate, so a region queried after a loop closure lands on
  the corrected map.
- **Depth cap reused from `max_depth_m`**: far stereo points are noise-dominated; no
  downsampling otherwise.
- **Complexity 5**: planned as one PR (the developer asked for the full process on one
  branch; a stack was not discussed). A natural split, if review prefers:
  (1) sidecar v4 + backend `region_points`, (2) proto + CM5, (3) demo.

## Validation Results

- **Baseline (fresh `main` @ `c126ded`)**: ruff, format, mypy strict green; pytest 636
  passed / 3 skipped.
- **Red**: `pytest --continue-on-collection-errors` → 4 failed, 634 passed, 3 skipped, 6
  collection errors. The six errors and three proto failures are this change's red tests.
  The fourth failure, `test_survey_cm5_rtabmap_e2e.py::test_euroc_pairs_stream_real_rtabmap_poses_and_points`
  (`TimeoutError`), is pre-existing and load-sensitive: it passed on the untouched base
  and in 2/2 isolated re-runs with this branch's tests present.
- **Lint at red**: `ruff check tests` reports I001 in the six new files only because
  `surmap.slam.regions` does not exist yet (sorted as third-party); `mypy` likewise fails
  on the missing module. Both clear when the module lands in Green; no ignore added.
- **Green (2026-10-31)**: ruff, format, mypy strict green; `SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1
  uv run pytest -q` → 680 passed, 3 skipped (the real-container streaming and region e2e
  ran). Sidecar image `surmap/rtabmap-stream:99d17b40764f` built locally.
- **Region probe** (EuRoC fixture, 376×240, frame 85, amd64 emulated on Apple Silicon):
  centre 140×100 box → 15 330 points (ch0, 65 ms) / 15 578 (ch1, 36 ms) vs 40 sparse
  inliers; whole 336×200 box → 67 066 (ch0, 138 ms) / 70 229 (ch1, 162 ms) vs 140 sparse;
  channel-1 → channel-0 nearest-neighbour median 0.7 cm, p90 1.8 cm; frame 1 `expired`
  with a 2 s ring. Point counts can exceed the raw box's pixel count: the polygon maps to
  a slightly larger area in the rectified image.
- **Demo probe** (cached EuRoC V1_01, 200 frames from index 300, `CentredBoxVideoSamDetector`,
  live sidecar): 200 `sam` and 200 `region` events; 199 regions `ok`, 8 289–8 775 points
  each (median 8 761); the last SAM result is released after the sidecar's stdin closed,
  so its query fails and that region is omitted (empty `regions`).

### Decided during Green

- **Implementation names differ from the plan**: the fake SAM is `CentredBoxVideoSamDetector`
  (`survey/sam.py`: track 1, centre 30 % of each frame) rather than a configured
  `InMemoryVideoSamDetector`, so the polygon follows each scene's display size. The demo
  checks the backend against `RegionPointSource` instead of extending `LiveSlamBackend`,
  so existing live-backend doubles without `region_points` keep working.
- **Version-pinned tests updated** (planned contract change): `test_slam_stream_protocol.py`
  `test_protocol_version_is_three_…` became `test_a_current_sidecar_is_accepted_and_a_pre_region_one_is_not`
  (v4 accepted, v3 rejected); the rectification test's ready line moved to version 4.
- **Red-test defect fixed**: `test_a_region_query_is_written_ahead_of_pairs_still_queued`
  keyed requests by `frame_id`, which region headers also carry; it now keys regions by
  `query_id` (assertion unchanged).
- **Tests added during Green** for the CM5 live mode (not in Red): it needs a calibration
  dir; it starts the streaming sidecar at the frame size with scaled cameras and serves
  regions.
- **Demo regions are queried synchronously** when a `sam` event is released (timeout 2 s;
  a failed query omits that region); SAM results are rare relative to frames. Region events
  are capped at 50 000 points for the browser, evenly sampled.
- **CM5 live mode**: `StreamSurvey` gets a pose only once that frame's odometry has arrived;
  scene points still arrive via `flush()` at stream end, as in batch mode.
- **Sidecar SGBM**: block 5, `numDisparities = max(64, width/5 rounded up to 16)`, P1/P2
  8·b²/32·b², uniqueness 10, speckle 100/2, `MODE_SGBM`; computed on the polygon's rows ± block.
