# Changeset: Simulation preview — overview, then FPV with RTAB-Map keypoints

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — three packages (Bevy crate, Python bridge, chat), a wire addition to the bridge `status` reply, async odometry ↔ held-frame matching
**PRD**: [2026-11-04-sim-preview-fpv-keypoints-prd.md](2026-11-04-sim-preview-fpv-keypoints-prd.md)

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests, committed · pytest 5 + 6 red, cargo 14 red (stubs), vitest 5 red
  - [x] Python: `encode_status` carries per-frame odometry keypoints; `DroneSession` reports each polled odometry's keypoints in raw pixels, in bounds
  - [x] Bevy: `view_mode` (`?view=preview`), `preview_view` (overview ↔ FPV from the viewed drone's phase), `parse_odometry`, `HeldFrames`, `depth_colour`
  - [x] Chat: the preview iframe opens `view=preview&fleet=1` (+ `bridge=` when known); "Open simulation" stays the full page
  - [x] `scripts/dev.sh --bridge`: agent gets `--bevy-bridge-port`, chat gets the bridge URL, the RTAB-Map image is prepared first (a failure stops the stack)
- [wf 3] ⏳ `/green` Green — implement until every red test passes ·
  - [ ] `rectified_to_raw` moved to `surmap.slam.keypoint_pixels`, the demo imports it from there
  - [ ] Bridge `status` reply: `odometry: [{frame_id, keypoints: [[u, v, depth], …]}]` (only when non-empty)
  - [ ] Bevy preview mode: one full-frame view, no header/hint/panel/HUD/button; overview (chase + PTZ) on the ground, FPV in the air
  - [ ] Bevy FPV: held left frames by `frame_id`, shown with their keypoints once odometry arrives; live left eye without a bridge
  - [ ] Chat: `bridgeUrl` from `?bridge=` or `VITE_SURMAP_BRIDGE_URL`, passed to the pane
  - [ ] `scripts/dev.sh --bridge` (`SURMAP_DEV_BRIDGE_PORT`, default 8790), RTAB-Map image prepared first (`SURMAP_DEV_RTABMAP_INIT_CMD`)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/simulation/bevy-simulation.md` — preview mode and the status reply's `odometry`
  - [ ] `docs/simulation/changelog/` entry
  - [ ] Python gates (ruff format/check, mypy, pytest), chat gates (lint, typecheck, test), `cargo test`, `trunk build`

## Initial Discovery

[2026-11-04-sim-preview-fpv-keypoints-initial-discovery.md](2026-11-04-sim-preview-fpv-keypoints-initial-discovery.md)

## State A

The chat pane embeds the full simulation page (`/sim/?scenario=<id>`): page header, hint, chase
view, stereo panel with calibration text, HUD text and the Take off button, all in one small
iframe. The bridge's `status` reply carries counts only; RTAB-Map's odometry keypoints stop at the
Python session. `scripts/dev.sh` never starts the bridge.

## State B

- **Bevy page, `?view=preview`.** `index.html` hides its header and hint and fills the viewport
  with the canvas. The app spawns no stereo panel, HUD or Take off button. `preview::PreviewView`
  is `Overview` while the viewed drone is docked / not engaged (chase camera active, PTZ as on the
  full page) and `Fpv` while it is airborne: the chase camera is switched off and a full-window
  image shows the FPV frame with a dot layer for its keypoints.
- **FPV frame.** Without a bridge: the live left eye. With one: each pair the page sends also keeps
  its left eye's colour pixels in `HeldFrames` (bounded, by `frame_id`); the `status` reply's
  `odometry` entries are matched to held frames, and the newest matched frame is shown with its
  keypoints (positions as a fraction of the frame, colour from depth). Older held frames are
  dropped.
- **Wire.** `BridgeStatus.odometry: tuple[FrameKeypoints, …]` — `FrameKeypoints(frame_id,
  keypoints: tuple[(u, v, depth_m), …])`, raw left-camera pixels within the frame. JSON:
  `"odometry":[{"frame_id":7,"keypoints":[[u,v,d],…]}]`, omitted when empty (goldens unchanged).
  `DroneSession` fills it from the odometry updates it polls for that pair, mapping rectified →
  raw with the backend's `rectification` (the demo's mapping, moved to
  `surmap.slam.keypoint_pixels`).
- **Chat.** `SimulationPane` gets `bridgeUrl?`; the iframe opens
  `<scenario url>&view=preview&fleet=1[&bridge=<url>]`; "Open simulation" opens the scenario URL
  unchanged. `App` reads `?bridge=` or `VITE_SURMAP_BRIDGE_URL`.
- **dev.sh.** `--bridge` first runs `scripts/build_rtabmap_stream.py` (overridable as
  `SURMAP_DEV_RTABMAP_INIT_CMD`; a failure stops the stack before any service starts), then adds `--bevy-bridge-port $SURMAP_DEV_BRIDGE_PORT` (8790) to the agent
  and runs the chat with `VITE_SURMAP_BRIDGE_URL=ws://127.0.0.1:<port>`.

## Delta

New: `surmap/slam/keypoint_pixels.py`, `examples/bevy-sitl-poc/src/preview.rs`. Changed:
`bevy_wire.py`, `bevy_bridge.py` (protocol `rectification`), `fleet/perception.py`,
`demo/server.py` (import), `fleet/stream.rs`, `fleet/bridge_wasm.rs`, `main.rs`, `index.html`,
`SimulationPane.tsx`, `App.tsx`, `ChatPage.tsx`, `scripts/dev.sh`.

## Verification

V1 — executable tests: pytest (wire + session), `cargo test` (pure preview/stream logic), vitest
(pane URL), `tests/test_dev_script.py` (dry run). V4 — manual: `scripts/dev.sh --bridge`, build a
scenario, see the overview in the pane, launch a drone, see FPV with keypoints.
