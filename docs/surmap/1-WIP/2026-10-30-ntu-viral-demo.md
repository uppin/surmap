# Changeset: NTU VIRAL outdoor drone scene

**Date**: 2026-10-30
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — new dataset format behind a new dependency, typed adapter, registry entry

## Workflow

- [wf 1] ✅ 2026-10-30 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
  - [x] Record initial discovery (dataset, calibration, reader)
  - [x] Add the user-approved `rosbags` dependency
  - [x] Create changeset
- [wf 2] ✅ 2026-10-30 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 7 red
  - [x] A ROS 1 stereo flight prepares into pairs named by left time
  - [x] A right image beyond the pairing skew is not paired
  - [x] The registry calibration becomes `sensor.yaml` (intrinsics, distortion, baseline)
  - [x] The unpacked bag does not stay in the cache
  - [x] Progress reports unpacking (bytes) then converted images
  - [x] Registry entry `ntu-viral-sbs-01` with the authors' calibration and credit
  - [x] A prepared flight plays through the demo
  - [x] Run the new tests (verify they fail for missing implementation)
- [wf 3] ✅ 2026-10-30 `/green` Green — implement until every red test passes · 576 passed, 2 skipped; EuRoC real-container e2e green; sbs_01 tracked end to end
  - [x] `ros1-stereo` format: unpack bag, typed image adapter, nearest-stamp pairing, PNG frames, sensor.yaml
  - [x] Page shows the unpacking phase
  - [x] Registry entry with depth tuning for an outdoor plaza
  - [x] Real run on sbs_01: left/right orientation confirmed, map, overlay, detector recorded
  - [x] Odometry resets one frame after losing track (`Odom/ResetCountdown=1`, added: default 0 never recovers)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] `README.md` §Demo — NTU VIRAL scene, attribution and licence
  - [ ] Changelog entry `docs/surmap/changelog/2026-10-30-ntu-viral-demo.md`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-30-ntu-viral-demo-initial-discovery.md).

## Stack Context

Stacked on `feat/map-camera-indicator` (changeset `2026-10-30-map-camera-indicator.md`).

## Affected Packages

- **surmap**: `demo/datasets.py`, `demo/page.py`
- **repo**: `pyproject.toml` / `uv.lock` (`rosbags`, user-approved)

## Summary

Adds an outdoor drone scene — NTU VIRAL `sbs_01`, a UAV flight over a
campus plaza — read from its ROS 1 bag and converted once into the
demo's EuRoC layout with the dataset authors' calibration.

## Technical Changes

### State A (Current)

- Scenes: EuRoC (indoor drone) and KITTI (outdoor car); formats `euroc`
  and `kitti-raw`.

### State B (Target)

- `DatasetSpec.ros1_stereo: Ros1Stereo(left_topic, right_topic, left,
  right: CameraCalibration, max_pair_skew_ns=5 ms)`.
- `dataset_format="ros1-stereo"`: the bag is unpacked from the zip into
  a temporary file in the cache (progress `unpacking`, bytes), its
  `sensor_msgs/Image` messages on the two topics are read through a
  typed adapter, each right image pairs with the nearest left image
  within the skew, both are written as 8-bit PNG named by the left
  stamp (progress `extracting`, images), `sensor.yaml` is written per
  camera from the registry calibration, and the bag is deleted.
- Registry entry `ntu-viral-sbs-01` (Hugging Face host, size + SHA-256
  pinned), 10 Hz, display 376×240, outdoor depth tuning, credit with
  CC BY-NC-SA 4.0.

## Verification

**Method:** V1 fail→pass and a recorded real run.
**Command:** `uv run pytest -q tests/test_demo_ntu.py`; live probe on sbs_01.
**Before:** new tests fail.
**After:** tests green; full gates green; probe numbers recorded at wrap.

## Decisions & Trade-offs

- **`rosbags` dependency (user decision)** over a hand-written ROS 1 bag
  reader.
- **Calibration from the dataset authors' VINS-Fusion config**, pinned
  in the registry, since the sequence zip carries none.
- **Bag unpacked to disk, then deleted.** `rosbags` needs a seekable
  file; peak disk is zip + bag + frames, and only the frames stay.
- **Stereo roles measured, not taken from topic names.** Mapped by name
  (`/left/image_raw` as stereo left), odometry lost 299/300 frames mid
  flight; with `/right/image_raw` as stereo left it lost 1/300 (frames
  1200–1500). Each topic keeps its own calibration; only the roles swap.
- **`Odom/ResetCountdown=1` by default for the streaming sidecar.**
  RTAB-Map's default 0 never resets lost odometry: sbs_01 lost 719 of
  1200 frames and the last ~140 s untracked. With 1: lost 0/3325 over the
  whole flight, keypoints on 3314 frames. EuRoC e2e still green.
- **Real run measured** (whole sbs_01, 3540 pairs, emulated sidecar):
  9.4 fps shown, odom+SLAM 72 ms median, 215 pairs dropped; detections
  person 1586, car 68, truck 80. Trajectory reaches ~15 m from the start
  against the Leica ground truth's 24.9 m (path 202 m, span 16 × 29.5 ×
  5.3 m): tracked throughout but ~40 % short — thin depth at 376 px
  (`fx·b ≈ 55 px·m`, features ~22 m away); full 752 px would double it
  but needs a native sidecar (72 ms of a 100 ms budget already).
