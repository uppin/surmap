# Changeset: Map-frame moving-object snapshots at RTAB flush

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — sidecar flush integration, real-RTAB E2E, one package

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-pr-stack` Plan — changeset, initial discovery · PRD = design doc (n1), §4 steps 6–7
  - [x] Record initial discovery
  - [x] Cross-check `docs/todo/` and `docs/code-issues/` — none exist for `src/surmap`
  - [x] Create/update PRD documentation — design doc on n1 serves as PRD
  - [x] Create changeset
- [wf 2] ✅ 2026-10-27 `/plan-pr-stack` Red — owned stubs + failing tests committed · commit 2; red: 3 failed in `tests/test_moving_placement.py` (plus inherited red)
  - [x] Stub: `placement.py` (correction distribution, snapshot construction)
  - [x] Failing tests: correction distribution on a known trajectory; snapshot designation/identity rules
- [wf 3] ✅ 2026-10-27 `/green` Green — implement until every red test passes · inline green; placement tests 3 passed, mypy+ruff clean. `distribute_correction`, `object_track_id`, `build_snapshot` implemented and unit-proven
  - [x] Flush wiring in `stream_moving_areas` + static-layer re-seeding at flush (post-green fix `677b931`), and the KITTI stereo E2E through real `SidecarRtabmapBackend` (`tests/test_moving_kitti_e2e.py`, this node): 8 RTAB keyframe poses over a 27.7 m trajectory, car-proximate candidate clusters on all 8 keyframes, graduated track with 44 snapshots, nearest snapshot 1.32 m from a labelled car. Findings recorded in Verification: RTAB's exported cloud is near-empty at driving depths (56 points), so the layer seeds from segment hit-counts; integer-disparity depth shells blocked differencing until subpixel refinement landed in PR #25
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/moving-object-detection-design.md` §6 — record KITTI placement results + streak measurement

## Initial Discovery

Full exploration: [2026-10-27-moving-placement-initial-discovery.md](./2026-10-27-moving-placement-initial-discovery.md).

## Stack Context

**Stack**: moving-object detection · slug **`#moving-objects`** — this PR is **5 of 6** · [#23](https://github.com/uppin/surmap/pull/23)
**Branch**: `pr-5-moving-placement` · **Base**: `pr-4-moving-classification`
**Successor**: `pr-6-moving-governance`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = `/plan-red` stubs + failing tests

Why the boundary falls here: map-frame placement is only
possible at flush time and is the point where the design meets
real RTAB-Map output.

### Owned API surface

- `src/surmap/moving/placement.py`
- Flush wiring in `src/surmap/survey/cm5_server.py` (snapshot publication)
- `tests/test_moving_placement.py`, KITTI stereo E2E

### Green wave

**Wave:** 3 of 3
**Node:** n5
**Concurrent with:** n6
**Blocks:** nothing

### Greenable independently?

**no — needs n4 green** (buffer + verdicts are its inputs).

### Trunk-merge safety

**When this PR merges alone:** snapshots appear on the
moving-areas stream at flush; survey/detections streams
unchanged. **Local dev data:** no. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| Observation buffer, verdicts, keypoints | n4 | stub/red until n4 greens | consumes them; never re-implements tracking |
| `StaticLayer` refresh, areas | n3 | real after n3 | calls refresh at flush |
| KITTI snippet fixtures | n2 | real after n2 | stages the E2E input |

**Greenable independently?** no — needs n4 green first

## Summary

Implements design steps 6–7: retrospective map-frame placement
of buffered moving-object observations at RTAB flush, published
as snapshots on the moving-areas stream.

## Background

Poses arrive late (design §1): moving objects can only be
placed in the map frame after the sidecar flush, from buffered
camera-frame evidence.

## Scope

- VO-increment correction distribution + map-frame transform
- Snapshot construction/publication; verdict confirmation at flush
- KITTI stereo E2E through the real sidecar; EuRoC end-to-end

## Technical Changes

### State A (Current)

- Areas/verdicts/keypoints exist live; nothing is placed in the map frame.

### State B (Target)

- At flush, one `MovingObjectSnapshot` per buffered observation,
  map-frame keypoints under existing designations.

### Delta

- New `placement.py`; flush wiring in the CM5 server.

## Verification

**Method:** V1-fail→pass — placement unit tests + KITTI stereo E2E via real `SidecarRtabmapBackend`
**Command:** `uv run pytest -q tests/test_moving_placement.py` + KITTI E2E (`SURMAP_REQUIRE_RTABMAP_E2E=1`)
**Before:** baseline 432 passed on n1; red run 3 failed in this node's tests — NotImplementedError from stubs
**After:** movers' snapshots within annotated extent; poses/cloud real; full gates green

**KITTI stereo E2E (executed 2026-10-27, this node):**
`SURMAP_REQUIRE_KITTI_E2E=1 uv run pytest -q -s tests/test_moving_kitti_e2e.py` → 1 passed in ~25 s.
KITTI tracking 0020, frames 0–79 staged into the real sidecar: 8 keyframe poses,
27.7 m trajectory, RTAB exported cloud = 56 points (near-empty at driving depths,
independent of export max-depth/decimation — the design's "seed the layer from the
RTAB cloud at flush" premise does not hold for this sidecar export; the E2E seeds
from voxels observed by ≥2 keyframes instead). Posed keyframes reconstructed with
`StereoReconstructor(match_width_px=400)` + subpixel disparity (PR #25; integer
disparity shells 2–9 m wide at car range made static points unrepeatable across
frames). Best labelled car carried 17 in-box stereo points; candidate clusters
landed within 4 m of a labelled car on all 8 keyframes; one track graduated to
RIGID_MOVER and produced 44 map-frame snapshots, the nearest 1.32 m from a
labelled car centre. Streak measurement: not applicable to this export (no dense
cloud to streak); recorded as an open item for the station-side cleanup path.

## Post-green review fix (2026-10-27)

- Stream assembled in `stream_moving_areas`: verdicts from
  `TrackMotionStats`/`VerdictMachine`, keypoint buffering for
  rigid movers, dwell-gated layer extension (`observe_frame`),
  and flush-time snapshots via `distribute_correction` when a
  SLAM backend is present. Handler-level proof:
  `tests/test_moving_stream.py` (fake stereo + batch fake SLAM;
  areas graduate to RIGID_MOVER, snapshots land at flush under
  area-allocated designations). Still deferred: the KITTI stereo
  E2E through the real sidecar (needs the n2 dataset spikes).
