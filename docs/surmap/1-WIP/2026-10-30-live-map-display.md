# Changeset: Live RTAB-Map display, overlay and throughput

**Date**: 2026-10-30
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: changes
**Complexity**: 4 — sidecar protocol bump (C++ + Python), host map state to numpy, demo overlay source swap, detector worker thread, page rendering

## Workflow

- [wf 1] ✅ 2026-10-30 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
  - [x] Record initial discovery (code reads + runtime probes)
  - [x] Create changeset
- [wf 2] ✅ 2026-10-30 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 13 red (3 protocol, 6 streaming, 4 demo), 18 existing green
  - [x] Protocol: coloured keyframe points decode; ready version 2
  - [x] Streaming: keyframes absent from the newest graph leave the map and the count
  - [x] Streaming: `map_cloud()` returns map-frame points with their colours
  - [x] Streaming: `latest_pose()` returns the newest odometry pose
  - [x] Streaming: pairs travel as raw `gray8`
  - [x] Streaming: `docker run` and `docker build` pin `--platform linux/amd64`
  - [x] Demo: map event plots the floor plane (x, z) with per-point colour
  - [x] Demo: live overlay projects RTAB-Map points into the current camera, coloured by depth
  - [x] Demo: the live overlay never runs the numpy stereo matcher
  - [x] Demo: a slow detector does not stall playback; detections still arrive after their frame
  - [x] Run the new tests (verify they fail for missing implementation)
- [wf 3] ✅ 2026-10-30 `/green` Green — implement until every red test passes · 533 passed, 2 skipped; real-container e2e green on `surmap/rtabmap-stream:4a4a0d3208b8`
  - [x] Sidecar: emit a keyframe only for a node present in the optimized graph; `[x,y,z,r,g,b]` points; ready v2
  - [x] Protocol v2 + `KeyframeUpdate.colors`
  - [x] Streaming backend: numpy map cloud cache, graph-authoritative keyframes, `latest_pose()`, gray8 pairs, platform pin
  - [x] Build script uses the shared build argv
  - [x] Demo: floor-plane map with colours; RTAB-Map overlay; detector worker; map event from numpy
  - [x] Page: per-point map colour, legends, accurate stream-error text
  - [x] Rebuild the sidecar image; real-container streaming e2e green
  - [x] Fixture script pulls the pinned image for `linux/amd64` (added: same arm64 failure)
  - [x] Sidecar caps keyframe points at 6 m depth (added: far-point outliers stretched the floor plan to 25 × 28 m)
- [wf 4] ✅ 2026-10-30 `/red` Red — review feedback: stable keypoint overlay, depth colour ramp · 10 red (3 protocol, 2 streaming, 5 demo); 2 map-projection overlay tests replaced
  - [x] Protocol v3: ready carries the rectification; odom carries the frame's inlier keypoints
  - [x] Streaming: rectification and per-frame odometry (with keypoints) exposed
  - [x] Demo: rectified keypoints map to raw display pixels through rotation + radial-tangential distortion
  - [x] Demo: a live frame is shown with its own frame's keypoints, once its odometry arrived
  - [x] Demo: a frame whose pair was dropped is still shown, without keypoints
  - [x] Demo: depth colour ramp — red near, orange mid, teal far — shared by overlay and legend
  - [x] Run the new tests (verify they fail for missing implementation)
- [wf 5] ⬜ `/green` Green — keypoint overlay and colour ramp ·
  - [ ] Sidecar: `OdometryInfo` inlier keypoints with depth; rectification in ready; v3
  - [ ] Host: protocol v3, per-frame odometry buffer
  - [ ] Demo: frame hold-back until odometry, keypoint overlay, map-projection overlay removed
  - [ ] Page: per-point overlay colour from the server; legend from the same stops
  - [ ] Rebuild the sidecar image; real-container e2e asserts keypoints arrive
- [wf 6] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] `README.md` §Demo — overlay source, colours, Apple Silicon note
  - [ ] Changelog entry `docs/surmap/changelog/2026-10-30-live-map-display.md`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-30-live-map-display-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: `slam/stream_protocol.py`, `slam/streaming.py`, `demo/server.py`, `demo/page.py`
- **deploy**: `deploy/rtabmap-stream/main.cpp` (image tag changes with the source hash)
- **scripts**: `scripts/build_rtabmap_stream.py`

## Summary

Makes the live demo map a real floor plan of the room, built only from
the keyframes RTAB-Map keeps, drawn in true point intensity; replaces the
unrectified numpy matcher overlay with RTAB-Map's own points projected
into the current view and coloured near→far; moves the detector off the
frame loop; and makes the sidecar build and run on Apple Silicon.

## Scope

In: the four user requests on the live demo (map display, RTAB-Map
near/far overlay, throughput, colour), plus the arm64 platform pin found
while running it.

Out (separate PR): a Metal / CoreML detector backend via ONNX Runtime's
`CoreMLExecutionProvider` — needs a model spike (the Coral INT8 TFLite
models use a TFLite-only post-processing op). The CM5 server, batch
sidecar and `StereoReconstructor` itself are unchanged.

## Technical Changes

### State A (Current)

- Sidecar emits a "keyframe" for every frame whose `getLastLocationId()`
  advanced, including nodes RTAB-Map then drops (400 emitted vs 45 graph
  nodes on 400 frames). Points are `[x,y,z]`, optical frame, no colour.
- Host stores ≤1000 points per emitted keyframe and rebuilds the map as
  Python `Vec3` tuples on every map event (16 → 286 ms, growing).
- Demo plots `(x, y)` of optical-frame points — a frontal view, not the
  floor plane. Map drawn flat grey.
- Overlay comes from `StereoReconstructor` on unrectified display frames
  (≈50 ms/frame, inaccurate near/far).
- Detector runs inline on the frame loop (≈19 ms/frame).
- Pairs are re-encoded to PNG per channel before sending.
- Sidecar image cannot be built on arm64 hosts.

### State B (Target)

- **Protocol v2.** `ready.version == 2`. Keyframe `points_local` entries
  are `[x,y,z,r,g,b]` (colour sampled from the left rectified image;
  grey cameras give r=g=b); `[x,y,z]` still decodes, with no colour.
  `KeyframeUpdate.colors: tuple[tuple[int, int, int], ...]` parallel to
  `points_local` (default grey when absent).
- **Sidecar** emits a keyframe only when its node is in
  `getLocalOptimizedPoses()` after `process()`.
- **Host map state.** Each `GraphUpdate` is authoritative: keyframes
  whose node is absent from a non-empty graph are dropped from the map
  and from `keyframe_count`. `map_cloud() -> MapCloud(points (N,3)
  float32, colors (N,3) uint8)` in the map (optical-world) frame, cached
  per keyframe by pose; `map_snapshot()` keeps its shape, built from it.
  `latest_pose() -> tuple[int, Pose] | None`. Pairs are sent as raw
  `gray8`. `docker run` / `docker build` pass `--platform linux/amd64`
  (the pinned image's only platform; a no-op on amd64 hosts).
- **Demo.** Map events plot the floor plane: `[x, z, r, g, b]` per
  cloud point and `[x, z]` per trajectory pose. With a live backend the
  frame overlay is the map cloud projected into the camera at the newest
  odometry pose (`depth = camera-frame z`), sampled to
  `MAX_OVERLAY_POINTS`; the numpy matcher is not run. Without RTAB-Map,
  or in batch mode, the overlay keeps the matcher. The detector runs on a
  worker thread with a latest-only slot; detections events follow their
  frame event and are drained at the end.
- **Page.** Map points drawn in their own colour; legends name the
  overlay source ("RTAB-Map points, coloured by depth"); the stream error
  text no longer blames another viewer.

### Delta (What's Changing)

| Area | Change |
|---|---|
| `main.cpp` | keyframe gate on graph membership; coloured points; ready v2 |
| `stream_protocol.py` | v2, optional colours |
| `streaming.py` | graph-authoritative keyframes, numpy cloud, `latest_pose`, gray8, platform pin, `stream_build_argv` |
| `demo/server.py` | floor-plane map, RTAB-Map overlay, detector worker |
| `demo/page.py` | per-point colour, legends, error text |
| `scripts/build_rtabmap_stream.py` | uses `stream_build_argv` |

## Verification

**Method:** V1 fail→pass (unit + demo tests) and a recorded runtime measurement.
**Command:** `uv run pytest -q tests/test_slam_stream_protocol.py tests/test_slam_streaming.py tests/test_demo.py`; real-container `tests/test_slam_streaming_e2e.py`; live probe over 600 EuRoC frames at 20 fps with the Coral detector.
**Before:** new tests fail; live probe 10.5 fps without the detector (3.8 fps observed with it at frame 1275); 595 keyframes for 600 frames; map spans x 6.0 / y 4.2 / z 8.1 m with y plotted.
**After:** tests green; full gates green; probe numbers recorded here at wrap.

## Decisions & Trade-offs

- **Python-side plane choice, not a sidecar base-frame transform.** The
  map stays in RTAB-Map's optical-world frame; the demo plots x–z. This
  keeps the overlay math (world → camera) trivial and avoids relying on
  whether `cloudFromStereoImages` applies the model's local transform.
  The floor plane is relative to the first camera pose (no IMU, so no
  gravity reference).
- **Overlay uses the raw display intrinsics** for projection; RTAB-Map's
  pose is of the rectified left camera (small rectification rotation,
  lens distortion ignored) — a few pixels of misalignment, accepted.
- **Numpy map cache instead of map deltas.** Concatenating cached
  per-keyframe arrays is cheap enough at demo scale; deltas would add a
  client-side protocol for no measured need.
- **Detector ordering contract changes.** Detections may now lag their
  frame by more than one frame event; the existing test's strict
  interleave becomes "each detections event follows its frame event".
- **E2E feeds at the recording rate.** `test_slam_streaming_e2e.py` fed
  90 pairs unpaced; it passed only because per-pair PNG re-encoding
  slowed the producer. With raw `gray8` the drop-oldest queue dropped
  71/90 pairs (measured; 0 at 20 Hz). The e2e now sleeps 1/20 s per
  pair, as real use does, and additionally asserts keyframes == graph
  nodes and > 50 distinct point intensities. No assertion was relaxed.
- **6 m keyframe depth cap in the sidecar.** At 376 px width,
  `fx·b ≈ 25 px·m`; points beyond 6 m come from 1–2 px disparities and
  stretched the live floor plan to 25 × 28 m (9.5 × 10.8 m after).
- **Overlay = odometry keypoints, not projected map points (review
  feedback).** Projecting the map from the newest pose sampled different
  points each frame, used a pose up to ~24 frames stale, and ignored lens
  distortion: points swam. Each frame now shows RTAB-Map's own inlier
  keypoints for that very frame (stable word ids on visual features),
  mapped rectified → raw through R1ᵀ and the radial-tangential model.
  Display therefore runs one SLAM latency behind playback.
- **Depth ramp inverted (pre-existing).** The page computed
  `hue = 180 - t·180`, drawing near points cyan and far ones red, opposite
  to its legend. The ramp now lives in Python (`depth_colour`) and the
  page only paints what it is sent.
