# Changeset: Simulation preview — on-board detections with non-overlapping labels

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — two packages (Python bridge + agent tools, Bevy crate), a proto contract addition (`set_onboard_model`), a wire addition to the bridge `status` reply
**PRD**: [2026-11-04-sim-preview-onboard-detections-prd.md](2026-11-04-sim-preview-onboard-detections-prd.md)

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Python: `encode_status` carries per-frame detections; `DroneSession` runs the chosen detector on the grey left frame and reports its detections; the registry applies a scenario's choice to its page, now and on a later hello
  - [ ] Agent: `set_onboard_model` sets, clears and refuses (unknown model / unavailable / unknown scenario); described to the model as SYNC · 10 s · FAIL
  - [ ] Bevy: `parse_detections`, `DetectionsByFrame`, `layout_cards` (no overlap, inside the image, just above when free), `detection_cards`, `draw_detections`
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Bridge `status` reply: `detections: [{frame_id, objects: [{label, score, box, track_id}]}]` (only when non-empty)
  - [ ] `DroneSession.use_detector`, `FleetPerception.use_detector`, `PerceptionRegistry.choose_detector`
  - [ ] `set_onboard_model` proto + handler, registered in `app.py`; `flying-the-fleet` skill and SYSTEM_PROMPT mention it
  - [ ] Bevy FPV: boxes and leaders drawn into the held frame, label cards as UI text laid out in display pixels
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/simulation/bevy-simulation.md` — the status reply's `detections`, the preview overlay
  - [ ] `docs/agent.md` — `set_onboard_model` in *Fleet tools*
  - [ ] `docs/simulation/changelog/` entry
  - [ ] Python gates (ruff format/check, mypy, pytest), `cargo test`, `trunk build`

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
