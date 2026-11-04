# Changeset: Simulation preview — on-board detections with non-overlapping labels

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — two packages (Python bridge + agent tools, Bevy crate), a proto contract addition (`set_onboard_model`), a wire addition to the bridge `status` reply
**PRD**: [2026-11-04-sim-preview-onboard-detections-prd.md](2026-11-04-sim-preview-onboard-detections-prd.md)

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests, committed · d748f44 — pytest 17 red, cargo 13 red (stubs)
  - [x] Python: `encode_status` carries per-frame detections; `DroneSession` runs the chosen detector on the grey left frame and reports its detections; the registry applies a scenario's choice to its page, now and on a later hello
  - [x] Agent: `set_onboard_model` sets, clears and refuses (unknown model / unavailable / unknown scenario); described to the model as SYNC · 10 s · FAIL
  - [x] Bevy: `parse_detections`, `DetectionsByFrame`, `layout_cards` (no overlap, inside the image, just above when free), `detection_cards`, `draw_detections`
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · pytest 2618, cargo 410, wasm check clean
  - [x] Bridge `status` reply: `detections: [{frame_id, objects: [{label, score, box, track_id}]}]` (only when non-empty)
  - [x] `DroneSession.use_detector`, `FleetPerception.use_detector`, `PerceptionRegistry.choose_detector`
  - [x] `set_onboard_model` proto + handler, registered in `app.py`; `flying-the-fleet` skill and SYSTEM_PROMPT mention it
  - [x] Bevy FPV: boxes and leaders drawn into the held frame, label cards as UI text laid out in display pixels
- [wf 4] ⛔ `/pr-wrap` Wrap — validate, clean up, verification, docs · V4 not run: the Superset pane stalls rAF on the full scene (fleet commands time out); needs a Chrome run — options: a) run V4 in Chrome, then wrap b) wrap on V1 only
  - [ ] Verification executed — result recorded
  - [x] `docs/simulation/bevy-simulation.md` — the status reply's `detections`, the preview overlay
  - [x] `docs/agent.md` — `set_onboard_model` in *Fleet tools*
  - [x] `docs/simulation/changelog/` entry
  - [x] Python gates (ruff format/check, mypy, pytest), `cargo test`, `trunk build`

## Initial Discovery

[2026-11-04-sim-preview-onboard-detections-initial-discovery.md](2026-11-04-sim-preview-onboard-detections-initial-discovery.md)

## State A

The bridge runs RTAB-Map and SAM (counts only) on the processed drone's frames; no on-board
model, and the agent cannot pick one for a live simulation. The `status` reply carries counts and
`odometry`. The preview's FPV shows the held frame with RTAB-Map keypoints only.

## State B

- **Agent.** `FleetTools.SetOnboardModel` (`set_onboard_model`: `scenario_id`, `onboard_model`)
  → `SetOnboardModelResponse { onboard_model (empty for none), streaming }`. It resolves the name
  with the station's `OnboardModels`, builds one source up front (so an unavailable model fails
  now), and stores the choice in the `PerceptionRegistry` under the scenario. `NOT_FOUND` unknown
  scenario, `INVALID_ARGUMENT` unknown model, `FAILED_PRECONDITION` unavailable model.
- **Perception.** `PerceptionRegistry.choose_detector(scenario, choice | None)` keeps the choice
  and applies it to the scenario's page now and to any page that registers later.
  `FleetPerception.use_detector` gives every drone session (and each one created later) its own
  fresh source (its own tracker). `DroneSession` runs it on each pair's grey left frame stacked to
  RGB; a detector failure skips that frame's detections and leaves the map running.
- **Wire.** `BridgeStatus.detections: tuple[FrameDetections, …]` —
  `FrameDetections(frame_id, objects: tuple[DetectedObject(label, score, box_xyxy, track_id), …])`.
  JSON: `"detections":[{"frame_id":7,"objects":[{"label":"car","score":0.82,"box":[x0,y0,x1,y1],"track_id":3}]}]`,
  omitted when empty (goldens unchanged).
- **Bevy preview.** The bridge stream keeps the recent detections by frame id
  (`DetectionsByFrame`) and attaches them to the `FpvFrame` it builds for an answered held frame.
  The FPV draws each box and its leader (dot at each end) into the frame's pixels, and a label
  card `<label> #<track> <score>%` per detection as UI text. Cards are laid out by `layout_cards`
  — the demo's `layoutCards` ported — in display pixels, so text never overlaps at any preview
  size; they are re-laid when the frame or the displayed size changes.

## Delta

Changed: `proto/surmap/agent/v1/fleet_tools.proto` (+ generated), `agent/tools/fleet_handlers.py`,
`agent/server/app.py`, `agent/skills/flying-the-fleet`, `simulation/bevy_wire.py`,
`simulation/fleet/perception.py`, `examples/bevy-sitl-poc/src/{preview.rs, fleet/stream.rs,
fleet/bridge_wasm.rs}`.

## Verification

V1 — executable tests: pytest (wire, session, registry, `set_onboard_model` handler over the real
server rig), `cargo test` (parse, layout, cards, drawing). V4 — manual: `scripts/dev.sh --bridge`
with a Coral model dir, launch a drone, `set_onboard_model`, see boxes and cards on the FPV.

## Validation Results

- V1, 2026-11-04: pytest 2618 passed / 38 skipped; `cargo test` 410; `cargo check --target
  wasm32-unknown-unknown` clean; `trunk build` OK; ruff, mypy (strict) clean.
- V4, 2026-11-04, not completed: an agent with `--bevy-bridge-port` and the real Coral fixture
  models served the preview in a Superset browser pane. `set_onboard_model` answered
  `ssd-mobilenet-v2`, the bridge socket connected and the FPV layer showed. After the worktree's
  pinned assets were copied in, the pane stalled `requestAnimationFrame`, so `launch_drone` timed
  out and no frame streamed. Still to do: the same run in Chrome.
