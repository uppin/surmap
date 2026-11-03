# Changeset: Camera calibration RPC (checkerboard) + sidecar covariance fix

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — proto/contract change, new package, sidecar process, BIDI streaming

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` (sidecar covariance P1)
  - [x] Red tests committed (calibration board/session/RPC, missing-module failures)
- [wf 2] ✅ 2026-11-03 `/green` Green — implement until every red test passes · 1794 passed, 36 skipped; sidecar Docker build green
  - [x] Proto: `CameraCalibrationService.StreamCalibration` (BIDI), explicit `CALIBRATION_TARGET_CHECKERBOARD`
  - [x] Simulated checkerboard renderer (known rig + board pose → stereo pair + ground-truth corners)
  - [x] OpenCV sidecar (detect + stereo solve over stdin/stdout) and Python session/guidance
  - [x] Fix `deploy/rtabmap-stream` odometry covariance
  - [x] Reopened by /validate-changes 2026-11-03: adaptive `cornerSubPix` radius + drift filter (RTAB-Map parity)
  - [x] Reopened: readiness gate on x/y/size/skew spread, not view count alone
  - [x] Reopened: an e2e test that solves from *detected* corners (and an anti-aliased simulator)
  - [x] Review fixes: per-eye EuRoC export with R/T and distortion; frame-size contract; unreadable frame and early finish keep the stream; right-eye corner order aligned to the left
  - [x] Odometry covariance prepared as RTAB-Map's RtabmapThread does (`odom_covariance.h` + C++ test run by the image build)
  - [x] RTAB-Map's optional features: multi-scale detection (≤ 3x), expected-baseline rescale, rational and fisheye lens models
  - [x] Capture plan as the first response; feedback names the filled viewpoint (developer request, 2026-11-03)
  - [x] Streaming-sidecar rational/fisheye support deferred with developer consent, 2026-11-03 (`src/surmap/docs/todo/2026-11-03-streaming-sidecar-lens-models.md`)
- [wf 3] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [x] Verification executed — result recorded (gates below)
  - [ ] Stable docs + changelog; delete this file and its discovery companion (at wrap, with the PR)

## Initial Discovery

See [the discovery companion](2026-11-03-camera-calibration-rpc-initial-discovery.md).

## State A → State B

- A: calibration is asserted (`StereoCalibration`, `*.camera.json`),
  never measured; the streaming sidecar feeds RTAB-Map identity
  odometry covariance.
- B: a BIDI `StreamCalibration` RPC takes stereo frames, returns
  per-view feedback plus a next-pose suggestion, and on `finish`
  returns the solved stereo calibration; a simulated checkerboard
  provides known-truth views for tests; the sidecar passes
  `info.reg.covariance` to `Rtabmap::process`.

## Verification

- Unit/RPC tests with a scripted detector; OpenCV end-to-end over
  simulated views (skipped without `cv2`, run where the sidecar
  environment provides it) recovering fx/baseline near truth.
- `uv run ruff check src tests`, `ruff format --check`, `mypy`,
  `pytest -q`.

## Implementation Progress

**Last Synced with Code**: 2026-11-03 (via /validate-changes, fixes and optional features applied)

| Item | Status |
|---|---|
| Proto `CameraCalibrationService.StreamCalibration` (spreads, `not_ready`, `FRAME_UNREADABLE`, R/T, lens, scale, baseline rescale, plan) | ✅ Complete |
| Simulated checkerboard (8x supersampled; radtan / rational / fisheye lenses) | ✅ Complete |
| OpenCV sidecar: RTAB-Map sub-pixel window + drift bound, ≤ 3x detection, radtan / rational / fisheye solves | ✅ Complete |
| Session: RTAB-Map measure, duplicate rule, readiness bar (fisheye size bar 0.25) | ✅ Complete |
| Capture plan (`surmap.calibration.plan`), matched viewpoints, plan-driven guidance | ✅ Complete |
| Expected-baseline rescale (`surmap.calibration.baseline`) | ✅ Complete |
| EuRoC export, radial-tangential only | ✅ Complete (no caller yet; rational/fisheye deferred with consent) |
| Sidecar odometry covariance (`odom_covariance.h`, C++ test in image build) | ✅ Complete (no new-map trigger on reset, by choice) |

## Validation Results

### Change Validation (/validate-changes)

- **Status**: ✅ after fixes · **Risk**: Medium (no real-camera run yet)
- Gates: ruff format/check, mypy strict, pytest (1843 passed, 33 skipped) all green;
  sidecar image builds and its covariance unit test passes; the three Docker SLAM
  e2e tests that skip without the image ran and passed.
- Compared against RTAB-Map `guilib/src/CalibrationDialog.cpp`, `corelib/src/RtabmapThread.cpp`,
  `corelib/src/Memory.cpp`, `corelib/src/Rtabmap.cpp` (introlab/rtabmap `37aec78`).
- Simulated results (solving from detected corners): pinhole fx 387.2 / baseline 71.5 mm
  (truth 381.36 / 70); barrel-distorted rig, radtan fx 380.2, k1 −0.249 (truth −0.25),
  baseline 70.3 mm; rational fx 380.0, baseline 70.4 mm; fisheye fx 260.2 (truth 260),
  baseline 70.5 mm; 2x upscaling finds a 3.4 px-square board native detection misses
  (0.20 px corner error). Following the capture plan fills all nine viewpoints and
  clears the bar at fx 300, 381 and 520.
- Remaining differences from RTAB-Map, by choice: whole board dropped on drift (views are
  dense grids, no corner IDs); every view needs both eyes (RTAB-Map also counts one-eye
  views for that eye's intrinsics); `min_views` default 8 (RTAB-Map 35 per eye); no
  new map on odometry reset.

## Refactoring Needed

### From /validate-changes (Code Quality)

- Done: dead PNG encode removed from `simulated.py`; bare `except` around
  `cornerSubPix` removed; `_feedback` takes one observation object.
