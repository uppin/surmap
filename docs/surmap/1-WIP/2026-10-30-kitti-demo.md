# Changeset: KITTI outdoor demo scene

**Date**: 2026-10-30
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — second dataset format + per-dataset display/depth tuning through demo, backend and sidecar

## Workflow

- [wf 1] ✅ 2026-10-30 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
  - [x] Record initial discovery (registry, display size, depth constants, KITTI access + licence)
  - [x] Create changeset
- [wf 2] ✅ 2026-10-30 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 14 red (12 KITTI demo, 2 streaming), 541 existing green
  - [x] Datasets: a KITTI raw drive + calibration zip prepare into EuRoC layout (pairs, timestamps, calibration)
  - [x] Datasets: the calibration zip is size + SHA-256 verified
  - [x] Datasets: the registry carries the KITTI drive with display size, rate, depth tuning and credit
  - [x] Demo: frames, calibration and sidecar use the dataset's display size
  - [x] Demo: overlay colours use the dataset's depth stops; the page shows its credit
  - [x] Demo: playback defaults to the dataset's rate; batch mode is refused without an IMU
  - [x] Streaming: hello carries the keyframe depth cap
  - [x] Run the new tests (verify they fail for missing implementation)
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `kitti-raw` extraction + calibration conversion
  - [ ] Per-dataset display size, fps, depth stops, depth cap, credit
  - [ ] Sidecar reads `max_depth_m` from hello
  - [ ] Registry entry `kitti-2011-09-26-drive-0009` with pinned hashes
  - [ ] Real run on the drive: map, overlay, detector recorded
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] `README.md` §Demo — KITTI scene, attribution and licence
  - [ ] Changelog entry `docs/surmap/changelog/2026-10-30-kitti-demo.md`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-30-kitti-demo-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Stack Context

Stacked on `feat/live-map-display` (changeset `2026-10-30-live-map-display.md`): needs its
protocol v3 sidecar, keypoint overlay and depth ramp.

## Affected Packages

- **surmap**: `demo/datasets.py`, `demo/server.py`, `demo/page.py`, `slam/stream_protocol.py`, `slam/streaming.py`
- **deploy**: `deploy/rtabmap-stream/main.cpp` (`max_depth_m` from hello)
- **scripts**: `scripts/demo.py` (rate default from the dataset)

## Summary

Adds an outdoor scene: a KITTI raw city drive, downloaded once from
KITTI's own host (SHA-256 pinned) and converted locally to the demo's
EuRoC layout, played at its native rate and size with depth tuning that
suits a street, and credited on the page with its licence.

## Technical Changes

### State A (Current)

- One registered scene (EuRoC V1_01, indoor); `ensure_dataset` accepts
  only `euroc`.
- Display 376×240, 20 fps, 6 m keyframe cap and 1/3/6 m ramp are global.

### State B (Target)

- `DatasetSpec` gains `calibration: ZipAsset | None`, `display_size`,
  `fps`, `depth_stops_m`, `max_map_depth_m`, `credit` (EuRoC keeps its
  current values as defaults).
- `dataset_format="kitti-raw"`: the drive zip's `image_00`/`image_01`
  PNGs become `mav0/cam0|cam1/data/<t_ns>.png` (cam0's timestamps name
  both, as KITTI sync pairs are index-aligned); the calibration zip's
  `calib_cam_to_cam.txt` becomes `sensor.yaml` per camera — intrinsics
  from `P_rect_0N`, resolution from `S_rect_0N`, zero distortion, `T_BS`
  identity for cam0 and `+b` along x for cam1 with
  `b = −P_rect_01[0,3] / P_rect_01[0,0]`.
- Registry entry `kitti-2011-09-26-drive-0009`: 620×188, 10 fps, stops
  5/15/40 m, cap 30 m, credit line with CC BY-NC-SA 3.0.
- Demo uses the dataset's size everywhere (frames, calibration, detector
  decode, sidecar hello, page canvas), its stops for overlay colours and
  legend, its credit on the page, its rate by default; batch mode raises
  for a dataset without IMU.
- Hello carries `max_depth_m`; the sidecar caps keyframe points with it
  (default 6 m keeps EuRoC unchanged).

## Verification

**Method:** V1 fail→pass and a recorded real run.
**Command:** `uv run pytest -q tests/test_demo.py tests/test_slam_streaming.py`; `scripts/demo.py --dataset kitti-2011-09-26-drive-0009` probe.
**Before:** new tests fail; `--dataset kitti-…` is not a choice.
**After:** tests green; full gates green; probe numbers recorded at wrap.

## Decisions & Trade-offs

- **Download from KITTI's host, convert locally, never re-host.** The
  user accepted KITTI's CC BY-NC-SA 3.0 / academic-use terms for this
  hackathon demo with attribution; re-hosting a subset was declined.
- **Grey cameras 00/01, not colour 02/03.** Same rectified geometry
  and the pipeline is grey; colour is a later option.
- **cam0 timestamps name both images.** KITTI sync frames are aligned by
  index; cam1's own stamps differ by microseconds.
