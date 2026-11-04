# Changeset: sim-disaster-2 sweep — the stack's correctness and visual-polish TODOs

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: changes
**Complexity**: 5 — Rust (flipbook particles, per-stand grass placement, per-window glow, metallic
packing, figure visor, screenshot pre-warm), Python (district-resolved floors, recorded dynamics
fixtures, a load-independent timing test), new CC0 textures, judged by screenshots

PRD: none (sweep of recorded TODOs; each TODO file is the requirement) · Discovery:
`2026-11-04-sim-disaster-2-sweep-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · these files (`/yolo-pr-stack` sweep)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/` (TODO gate answered)
  - [x] Create changeset
  - [x] Build and baseline healthy
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — failing tests for every testable item, committed · Rust 9 red (`sweep_tests.rs`: flipbook, prewarm, window glow, metallic packing, visor, per-stand grass), Python 4 red (district floors ×2, recorded dynamics ×2); 155 Rust inherited green
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes, then the visual items ·
  - [ ] C1 floors from the district preset (`2026-11-04-building-fire-floor-from-district`)
  - [ ] C2 recorded dynamics fixtures, end to end (`2026-11-03-fire-perimeter-capture-end-to-end`)
  - [ ] C3 per-stand grass seed (`2026-11-03-per-stand-grass-seed`)
  - [ ] C4 load-independent differencing budget (`2026-11-03-differencing-frame-budget-timing-flake`)
  - [ ] P1 flame-tongue flipbooks (`2026-11-03-flame-tongue-flipbook-sprites`)
  - [ ] P2 building texture character + metallic packing (`2026-11-04-building-texture-character`)
  - [ ] P3 per-window glow variation (`2026-11-04-building-window-glow-variation`)
  - [ ] P4 pre-warmed smoke in stills (`2026-11-04-building-smoke-prewarm-stills`)
  - [ ] P5 figure facing cue (`2026-11-03-figure-facing-cue`)
  - [ ] P6 fire light A/B (`2026-11-03-fire-light-visibility`)
  - [ ] Each solved TODO file deleted; screenshot set S1 taken
  - [ ] Gates green; `cargo test --locked`; `cargo check --target wasm32-unknown-unknown`; clippy clean in touched code
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (tests, V3 load run, planner-reviewed S1)
  - [ ] `docs/simulation/bevy-simulation.md` updated for every new field; changelog `2026-11-04-sim-disaster-2-sweep.md`; `HACKATHON.md` rows for new texture/flipbook sources
  - [ ] Lint (`--no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Stack Context

Stack slug `sim-disaster-2`: `main ← n3 #100 ← n4 #101 ← n5 #104 ← n6 feat/sim-disaster-2-sweep (this, sweep)`.

### Green wave

**Wave:** 4 of 4 · **Node:** n6 (sweep) · **Concurrent with:** none · **Blocks:** nothing ·
**Needs:** n3 (#100), n4 (#101), n5 (#104) — every item is a TODO those PRs recorded on their code.
**Greenable independently?** no.

## Background — the TODO gate (developer, 2026-11-04)

Carried here: **Correctness** (C1–C4) and **Visual polish round** (P1–P6). Deferred with consent
(recorded in each file): `2026-11-03-fire-eye-mount-pitch`, `2026-11-04-legacy-buildings-burn`.

## State B (after) — contracts

Everything tunable stays runtime JSON (developer: "everything should come declarative").

- **C1** `add_building_fire(manifest, id, *, building, floor, start_s=0, assets_dir=None)`: with
  `assets_dir`, a building without `floors` takes `floor(height / floor_m)` of the district holding
  its centre (later districts win), and the floor is checked against it. The store passes its
  `assets_dir`; `AddBuildingFire` answers `INVALID_ARGUMENT` on a floor past the resolved count.
- **C2** Two short real recordings, committed as fixtures without images when the loader allows
  (else the smallest `--jpeg`), each ≤ 2 MB: `tests/fixtures/bevy_capture_dynamics/evacuation/`
  (`wildfire-evacuation`) and `.../blaze/` (`downtown-blaze`), recorded with the native `--record`.
  They prove `fire_perimeter.jsonl`, `object_tracks.jsonl` and `building_fires.jsonl` end to end.
- **C3** `vegetation::grass_instances(stand, def) -> Vec<Vec2>` (ENU positions): a pure function of
  the stand (its own `seed`, rectangle, density) and species; the renderer instances exactly these.
  No global `WorldSeed` decides a stand's grass.
- **C4** `test_differencing_is_within_frame_budget` measures what does not depend on host load
  (process CPU time, or a fixed operation budget), keeping the 4 000-point / 5 Hz design budget.
- **P1** fx `flipbook: {texture, columns, rows, fps}` (texture `textures/fx/*.png`, CC0, pinned in
  `assets.lock.json`); flames and window flames ship one; particles animate through it.
- **P2** `textures::pack_metallic_roughness(roughness_rgba, metallic) -> rgba` (R 255, G roughness,
  B metallic·255, A 255) so roughness-only sets keep a preset's `metallic`; replacement CC0 sets for
  cement_block (grey CMU), copper (verdigris), plastic (PVC siding), wood (clapboard), eternit
  (fibre-cement corrugate); `uv_scale` checked per preset against the spec's real sizes.
- **P3** `look.json` `fire.glow_variation` (0.35) and `fire.glow_flicker_hz` (1.5);
  `FireLook::window_glow(building_seed, window, t_s) -> f32` in `[1 − v, 1 + v]`, seeded per
  window, flickering in time; each window's glow is scaled by it.
- **P4** fx `prewarm_s`: in screenshot mode an effect is advanced `prewarm_s` before the still, so
  plumes match the scene time; shipped smokes pre-warm at least their longest lifetime.
- **P5** `person.figure.json` `visor: {size_m, offset_m, colour}` — a dark visor on the head's front.
- **P6** A light-on / light-off still pair (W2 t=40, D2 t=400); the planner decides the lights'
  values from it (JSON).

## Verification

- **V1** — Rust and Python tests for C1, C2, C3, P1–P5's contracts.
- **V3** — C4: the differencing test passes 10/10 under synthetic CPU load (command recorded).
- **V4** (developer-consented: planner-reviewed screenshots) — **S1**: W2 t=40 overview + fire-eye,
  D2 t=400 overview + fire-eye, B1 t=60 people, D1 downtown/suburban/industrial, P6 pairs.

## Prerequisites

The TODO gate is this node's prerequisite scan; nothing else open touches these files.

## Decisions & Trade-offs

- One sweep PR for both groups: they touch the same JSON and screenshot runs; splitting would
  re-shoot twice.
