# Bevy disaster simulation — photo-real, runtime assets, live stereo to RTAB-Map - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy WASM disaster simulation (`examples/bevy-sitl-poc`, history
  `docs/surmap/changelog/2026-11-02-bevy-wasm-poc.md`)
- **Related Features**: [Disaster world](../disaster-world.md) (ground truth),
  RTAB-Map streaming sidecar (`docs/architecture.md`, `src/surmap/slam/streaming.py`),
  [PX4 SITL](../px4-sitl.md) (the capture → EuRoC path this mirrors)

## Summary

The browser simulation becomes a usable stereo source for SurMap: it looks like a real disaster
block (PBR textures, CC0 models, sky, shadows, atmosphere, a camera that behaves like a sensor),
loads its scene content at runtime, and streams the drone's stereo frames live to RTAB-Map — with
proof that RTAB-Map tracks them, builds a sparse map and answers dense polygon queries.

## Background

Developer request (2026-11-03): make the WASM Bevy simulation "as photo-realistic as possible",
stream its frames to RTAB-Map, and verify that RTAB-Map can use the simulated stereo for sparse
navigation and for dense points behind polygon queries. Follow-up: adding GLB assets must not
recompile the WASM — they are added at runtime (reference: scenic-engine's content-directory
pattern). Interview answers: live WebSocket **and** a recorded session; CC0 PBR assets fetched at
build time with pinned hashes; acceptance = a committed recorded capture through the real sidecar
plus a recorded live run.

## Proposed Changes

### What's Changing

- **Runtime scene content.** `examples/bevy-sitl-poc/assets/scene.json` lists environment (HDRI,
  sun, fog), PBR texture sets and model instances (GLB path, ENU position, yaw, scale, collider,
  ground-truth flag). The page fetches it and the GLBs at runtime; adding a model is: drop the
  `.glb` in `assets/`, add an instance to `scene.json`, reload. The WASM is not rebuilt.
- **Asset fetch.** `uv run python scripts/fetch_sim_assets.py` downloads the CC0 textures, HDRI and
  models pinned in `assets/assets.lock.json` (URL, sha256, licence, source page) into `assets/`;
  binaries are git-ignored.
- **Photo-realism.** Textured PBR ground/roads/rubble, CC0 GLB vehicles and debris, HDRI image-based
  light, physical sun with cascaded shadows, `Atmosphere`, distance fog, AgX tonemapping, physical
  exposure, bloom, TAA on the chase view; the stereo eyes keep geometry-stable anti-aliasing (no
  TAA jitter) plus a sensor model (exposure, vignetting, read noise). SSAO is excluded: Bevy 0.18
  does not support it on WebGPU.
- **Scripted survey flight** (`?flight=survey-loop` / `--flight survey-loop`): a deterministic
  kinematic loop over the block for repeatable captures. Manual flight is unchanged.
- **Frame capture and streaming.** Both eye targets are read back from the GPU, converted to 8-bit
  grey and sent with the rig's ground-truth ENU pose over a WebSocket (`?bridge=ws://…`) using a
  small binary wire format (`hello` with calibration, then `pair`s).
- **Bridge.** `uv run python scripts/serve_bevy_sim.py` serves the built page and `assets/` on one
  origin and runs the WebSocket bridge: each pair goes live into the RTAB-Map streaming sidecar;
  the page shows RTAB-Map's status (tracked, lost, keyframes); `--record <dir>` also saves the
  session (capture dir + EuRoC export + ground truth).
- **Native recorder.** `cargo run --release -- --record <dir> --flight survey-loop --frames N`
  writes the same capture format headlessly-in-a-window; `--screenshot <png>` saves a still.
- **Verification.** A committed short capture runs through the real sidecar in CI.

### What's Staying the Same

- The streaming sidecar, its protocol (v5) and image; the demo server; the Gazebo/PX4 path.
- Scope boundary: the simulated drone is the simulation's own; SurMap still has no flight-control
  path. RTAB-Map output is never fed back into the simulation.

## Impact Analysis

### Technical Impact

Example crate gains `web-sys`/`js-sys` (WebSocket, wasm only) and the Bevy features it needs.
No new Python dependency (`websockets` is already locked). CI: the streaming e2e job runs one more
test file; the Bevy jobs keep their commands.

### User Impact

Operators can rehearse the whole stereo → RTAB-Map → polygon-query path in a browser, with no
Gazebo and no drone.

## Acceptance Criteria

1. The committed capture streamed through the real sidecar: odometry posed on ≥ 90 % of frames;
   ATE RMSE ≤ 0.5 m against the ground-truth rig positions after a rigid (no-scale) alignment;
   ≥ 3 keyframes, a final graph, ≥ 2 000 sparse map points.
2. A polygon drawn around a ground-truth object's projection on a recent frame returns `ok` with
   ≥ 200 dense points, ≥ 80 % of them inside that object's box (grown 0.5 m) once mapped to ENU.
3. Adding a GLB is a content edit — proven by a test that the shipped manifest's every model and
   texture resolves to a pinned asset, and that the WASM build does not embed `assets/`.
4. A recorded live run (Chrome, WebGPU) where the bridge reports RTAB-Map tracking.

## Status

🚧 In Progress
