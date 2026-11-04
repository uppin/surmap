# Changeset: on-board COCO detectors find the simulation's cars and people

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — two packages (Rust simulation, Python `surmap.simulation`), new pinned assets, a recorded fixture, an opt-in e2e against real networks

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery (PRD ➖: simulation test asset, no product surface) · changeset + discovery companion @ `4abdb07`
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — failing Python and Rust tests, committed · Python: collection error (no `detection_eval`) + 3 failing; Rust: 7 compile errors on missing `colour`/`bgra_to_rgb8`/`frame_line`/`FigureModel`/`clip_time`/`person_truth` @ `4abdb07`
  - [x] Python: `detection_eval` (visibility, matching, report, colour-first detection) red
  - [x] Python: `load_bevy_capture` reads `left_rgb_ref`; lock pins keep `attribution` red
  - [x] Rust: `--colour` plan flag, `bgra_to_rgb8`, `frame_line`, figure `model`, `clip_time`, person ground truth, shipped humanoid and cars pinned red
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · pytest 2054 passed / 36 skipped; cargo test 182 passed; wasm32 check green
  - [x] Recorder writes colour left frames under `--colour` (grey frames unchanged)
  - [x] Survivors wear a rigged humanoid glTF (CesiumMan, CC-BY-4.0), posed from its walk clip on the sim clock, tinted with the coat (`coat_tint`, added after measuring the white figure lose to the capsules; red test first)
  - [x] People enter `ground_truth.json` as `person` boxes
  - [x] Covered cars replaced by CarConcept (CC-BY-4.0) with `normal_maps: false` (added after measuring the speckle; red test first); both pinned in `assets.lock.json` with attribution
  - [x] `scripts/score_sim_detections.py` scores a capture per profile; detections of objects too small to be in view are not false positives (red test first)
  - [x] New fixture `tests/fixtures/bevy_sim_detector_capture/` recorded; before/after measured
  - [x] Opt-in e2e `tests/test_sim_detector_realism_e2e.py` (`SURMAP_REQUIRE_CORAL_E2E`) in CI `coral-e2e`
  - [x] Served-scenario golden `tests/fixtures/sim_scenario/wreck-on-the-avenue.json` follows the shipped scene's new car entries
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/simulation/bevy-simulation.md` — colour recording, humanoid figures, person ground truth, car model, detector scoring, non-COCO kinds out of scope
  - [ ] `docs/simulation/changelog/2026-11-04-sim-onboard-detector-realism.md` written
  - [ ] Four gates green; `cargo test --locked` green
  - [ ] Changeset and discovery companion deleted from `1-WIP/`

## Initial Discovery

[2026-11-04-sim-onboard-detector-realism-initial-discovery.md](2026-11-04-sim-onboard-detector-realism-initial-discovery.md)

## Summary

Make the Bevy simulation realistic enough that the Coral COCO profiles detect its cars and
people, and measure it: uncovered car models, humanoid survivors, colour frames like the ELP
module's MJPEG stream, people in the ground truth, and a scorer that projects each ground-truth
box into every frame and counts visible-vs-detected and false positives.

## Technical Changes

### State A (Current)

Cars under a tarp, capsule people, grey-only recordings, no people in ground truth, no scorer.

### State B (Target)

- `--record … --colour` also writes `frames/left_rgb/<t_ns>.{jpg,png}` (RGB) and adds
  `left_rgb_ref` to each `frames.jsonl` line; grey eyes unchanged. `load_bevy_capture` exposes it
  as `CapturedFrame.left_rgb_ref`.
- `person.figure.json` `model: {glb, scale, yaw_deg, clip_s}` puts a glTF humanoid on every
  figure (the capsule stays as the fallback when no model is declared) and `body_m` sizes the
  `person` ground-truth box written for each survivor.
- `scene.json` cars are `models/car_concept/CarConcept.glb`.
- `surmap.simulation.detection_eval` + `scripts/score_sim_detections.py`.

### Delta

Additive everywhere; the existing grey fixture and its RTAB-Map e2e are untouched.

## Verification

**Method:** V1-fail→pass for the scorer and the recorder/figure contracts (unit tests); V3 for the
detection numbers — `uv run python scripts/score_sim_detections.py <capture> --threshold 0.3`
before (old fixture) and after (new fixture), recorded below; the opt-in e2e pins a minimum hit
rate on the new fixture.
**Command:** `uv run python scripts/score_sim_detections.py tests/fixtures/bevy_sim_capture --threshold 0.3` and the same over `tests/fixtures/bevy_sim_detector_capture`
**Before:** cars detected in 0/90 frames by every profile (probe, 2026-11-04).
**After:** recorded at wrap.

## Decisions & Trade-offs

- Assets come from Khronos glTF-Sample-Assets pinned at a commit: no CC0 car or person exists on
  Poly Haven, ambientCG carries materials only, and Sketchfab downloads need a token and give
  signed URLs that cannot be pinned.
- Colour is written beside grey rather than instead of it, so RTAB-Map's inputs do not change.
- Visibility ignores occlusion (no depth is recorded); the scorer counts an object visible when
  its projected box is mostly inside the image and big enough to detect.
