# Changeset: rigged, animated people

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — skeletal animation in Bevy 0.18 (`AnimationGraph`, players seeked to simulation
time), a pure clip-selection model, figure/manifest/station schema, pinned CC0 rigged glTF; one
native visual checkpoint

PRD: `PRD-2026-11-04-sim-rigged-people.md` · Discovery:
`2026-11-04-sim-rigged-people-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-pr-stack` Plan — PRD, changeset, initial discovery · these files @ `b3961e2` (`/plan-pr-stack` pass 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-11-04 `/plan-pr-stack` Red — acceptance and failing lower-tier tests, committed · Rust 20 red (+26 inherited from n1); Python 12 red (2 acceptance, 10 unit/it) — commit 2
  - [x] Build and baseline healthy — on n1's red commit: `cargo test --locked` 167 green / 26 red (all n1's), wasm check ok, `uv run mypy` clean; pytest pre-existing local failure `tests/test_survey_cm5_rtabmap_e2e.py` (RTAB-Map sidecar) not this stack's
  - [x] Stubs this node owns (`figure_anim.rs`, `Pose`, `RigDef`, `FigureDef.rig`, `Figure::posed`, `Person.pose`/`yaw_deg`/`height_m`/`glb`, `validate_people`, `Body.pose`, `surmap.simulation.people`, proto `PersonElement.pose`/`height_m`/`yaw_deg`)
  - [x] Acceptance tests written and failing for the right reason (`tests/test_sim_people_e2e.py`)
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · every owned red test green: Rust 249/249, Python 2110 passed; ruff, mypy, wasm check ok; detector bar met on the shipped pass (ssdlite 65/113 against Cesium Man's 38/113), standing and sitting; waving and lying missed after 3 iterations (TODO recorded)
  - [x] Pin the CC0 humans: `models/person/wave.glb` (Quaternius, idle/walk/run/wave/death as lie) and `sit.glb` (SitIdle), developer option 2b; the lock carries their animation names; Cesium Man's pin and credit dropped
  - [x] One humanoid concept: n2's `RigDef` merged into main's `FigureModel` (`rig`, `pose_models`, `model_for`); `StandIn`/`PersonLook` removed for `FallbackBody`/`FigureCoat`/`FigureSkin`; shipped `person.figure.json` model block with clips and the sit override; pose validation
  - [x] Rust `figure_anim.rs` (pure) and runtime `actors/rig.rs`: clips by speed and pose on the sim clock; seen in native stills (waving, sitting, walking)
  - [x] Tracks: `pose` on `Body`/`track_line`; a lying person's truth box is horizontal (`posed_person_truth`, red test first); Python capture loader reads `pose` (`object_poses`)
  - [x] Python `scenario_manifest`, preset `earthquake-survivors` (golden regenerated), proto `PersonElement`, handler
  - [x] Detector cross-check — `scripts/score_sim_detections.py` per-pose breakdown (red test first); both passes recorded and scored, 3 iterations, table in `docs/simulation/bevy-simulation.md`
  - [x] Waving and lying bar missed: TODO `examples/bevy-sitl-poc/docs/todo/2026-11-04-waving-and-lying-people-undetected.md`
  - [x] Gates: `ruff format`, `ruff check --no-cache`, `mypy`, `pytest -q`, `cargo test --locked`, wasm check
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (tests + native stills of `earthquake-survivors` reviewed)
  - [ ] `docs/simulation/bevy-simulation.md` — *The figure* rewritten for the rig and poses; `docs/agent.md` — person fields
  - [ ] `docs/simulation/changelog/2026-11-04-sim-rigged-people.md`
  - [ ] Lint (`ruff --no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Stack Context

Stack `sim-traffic` (slug `sim-traffic`) — **2 of 3** · PR [#107](https://github.com/uppin/surmap/pull/107).
**Kind:** Feature · adds — **Workflow:** feature preset; pass-2 route `/plan-red` Steps 7–9.
Branch `pr-2-sim-traffic`, base `pr-1-sim-traffic`; successor `pr-3-sim-traffic`.
Seam: the person figure (`actors.rs` figure look, `world.rs` `Builder::person`) and a new
`figure_anim.rs`; touches the track line only to add `pose`.
**Owned API:** `Person.pose` / `height_m` / `glb`, `Pose`, `FigureDef.rig` (`RigDef`),
`figure_anim.rs` (`locomotion`, `clip_time`, `FigureRig`), `Body.pose` on the track line, Python
person pose/height rules and `earthquake-survivors` preset, proto `PersonElement.pose` /
`height_m`.

### Green wave

**Wave:** 1 of 2 · **Node:** n2 · **Concurrent with:** n1 · **Blocks:** nothing.
Edges: `n1 → n3`; n2 needs nothing from n1 — it sits above n1 only because the line is the waves
concatenated with wave 1's blocker first.
**Greenable independently?** yes — its tests touch n1 only through the track line, and assert the
`pose` key alone, never n1's `kind`/`yaw_deg`.

### Inherited Dependencies — do not implement here

| Symbol | Owner | During this PR's green | This PR instead |
|---|---|---|---|
| `Element::Vehicle`, `vehicle.rs`, `VehicleElement` | n1 | stub until n1 greens | ignores them |
| track `kind` / `yaw_deg` on `Body` / `track_line` | n1 | stub fields | adds `pose` beside them; tests assert `pose` only |

**Greenable independently?** yes.

### Trunk-merge safety

Additive: `pose`, `height_m`, `glb` optional; a figure file without `rig` keeps today's capsule
figure, and a missing rig asset (not fetched) falls back to it, so CI and checkouts without
assets still render people. Manifest version 1; no SQLite schema change; no production data.

## Background

The developer (2026-11-04): "let's add realism to people …". Decisions the same day: CC0 rigged
glTF first with animation clips played; people are n2 of the `#sim-traffic` stack.

## State A (before)

`Builder::person` spawns a `Figure` root with a capsule (coat) and sphere (skin) child; a visor is
attached once `person.figure.json` loads; `animate_figures` sets yaw (eased) and a step bob. No
limbs, clips or poses. Track objects: `id`, `enu`, `action` (+ n1's `kind`, `yaw_deg`).

## State B (after)

### The figure (`assets/behaviour/person.figure.json`)

Gains an optional `rig`:

| Field | Meaning |
|---|---|
| `glb` | rigged human glTF (asset path) |
| `clips` | `{idle, walk, run, wave, sit, lie}` → the glTF's animation names |
| `walk_ground_m_s`, `run_ground_m_s` | ground speed each clip covers at rate 1 (no foot slide) |
| `run_above_m_s` | speed where locomotion crosses from walk to run |
| `blend_s` | crossfade between locomotion clips and into/out of a pose |
| `standing_height_m` | the rig's height at scale 1 |
| `coat_slots`, `skin_slots` | glTF material names that take the person's `coat` / `skin` material |

With a `rig`, the step bob and visor are not applied to the rig (the clips carry the gait and the
face shows the heading); `yaw_ease_s` still eases turns.

### A person in the manifest

```json
{"kind": "person", "id": "survivor-1", "position_enu": [-15.0, 31.0, 0.6], "yaw_deg": 30.0,
 "coat": "coat_yellow", "skin": "skin", "pose": "lying", "height_m": 1.68}
```

`pose`: `standing` (default) · `lying` · `sitting` · `waving`; `yaw_deg` (new, optional) faces a
posed person; `height_m` scales the rig (0.9–2.2); `glb` overrides the figure's rig for this person.
A person with a tree plays locomotion while it moves and its `pose` whenever it stands.

### Animation (`figure_anim.rs`)

Pure: `locomotion(def, speed_m_s, pose)` → weighted clips with playback rates (idle at 0; walk at
`speed / walk_ground_m_s`; walk→run crossfade around `run_above_m_s`; the pose clip when
standing and posed — `lie`/`sit` held at their last frame, `wave` looped). `clip_time(now_s,
phase, rate, duration)` — phase per id (`phase_of`), so a crowd is not in step. The app builds one
`AnimationGraph` per rig asset and **seeks** each `AnimationPlayer` to its clip time each frame
from `SimClock`, never letting it free-run, so a still at `--at t` and a recording are reproducible.

### Ground truth

Track objects that are people carry `"pose"`; a lying person's extent in any truth or track
consumer is horizontal (`kind` `person`, from n1). Static `ground_truth.json` is unchanged.

### Station and agent

`scenario_manifest.py` validates `pose`, `height_m`, `glb`, `yaw_deg`; `add_element` person takes
`pose` and `height_m`; preset `earthquake-survivors` = the disaster block with a survivor lying by
`collapsed-0`, one sitting on rubble at `collapsed-2`, one waving at `collapsed-3`, and two rescuers
walking a `follow_path` between them.

### Assets

Pinned in `assets.lock.json`, **CC0-1.0** only, source page recorded. Criteria: one glTF/GLB with
a humanoid skeleton and clips covering idle, walk, run, wave, sit and a lying/fallen pose (a
death/fall clip held at its last frame qualifies); separable clothing/skin materials. Candidates:
Quaternius characters (CC0; on Poly Pizza as GLB with clips, or via the Quaternius site). If no
pinnable CC0 file meets the criteria, the Green row halts ⛔ with the candidates found.

## Verification

- **V1** — Rust: `locomotion` picks idle/walk/run/pose by speed and pose, rates match ground speed,
  crossfade weights sum to 1; `clip_time` deterministic per (id, t); `FigureDef` with and without
  `rig`; manifest pose/height rules and the golden `earthquake-survivors.json`; track line `pose`.
  Python: pose/height validation mirrors Rust; preset; `add_element` person with pose; an
  acceptance test over the preset (posed people, rescuers with trees).
- **Supporting evidence (not a rung)** — native stills `--screenshot <dir> --at 20 --scenario
  earthquake-survivors` (`people.png`, `person-close.png`), reviewed at wrap.

## Red tests (commit 2)

| Test | Validates |
|---|---|
| `tests/test_sim_people_e2e.py` (2) | agent places a lying and a waving survivor → served, valid; preset served = golden `earthquake-survivors.json` (written at Green from the preset) |
| `tests/test_sim_people_manifest.py` | 6 refusals naming id + reason (pose, height ×2, yaw, glb ×2); preset poses and rescuers' trees; preset = golden. The 4 *may take each pose* cases are green before and after (accept cases guarding over-strict rules) |
| `tests/test_agent_simulation_tools.py` — person with pose/height/yaw; unknown pose `INVALID_ARGUMENT` | handler |
| `src/figure_anim/tests.rs` (12) | pose name; idle/walk/run by speed with ground-matched rates; crossfade sums to 1; poses held; posed-but-moving walks; `clip_time` loop/phase/hold; `rig_scale`; `RigDef::validate` |
| `src/actors/tests.rs` (4) | track `pose`; posed survivor without a tree tracked; shipped figure has a rig; bad rig refused by `FigureDef::from_json` |
| `src/scene_manifest/tests.rs` (4) | height range; `glb` override rules and asset path; golden parses with lying/sitting/waving |

- **V3** — deterministic recorded command, result recorded 2026-11-04 (score 0.3, colour):
  `uv run python scripts/fetch_coral_model.py`, then from `examples/bevy-sitl-poc`
  `cargo run --release -- [--scenario earthquake-survivors] --record <dir> --frames 75|200 --rate-hz 1
  --start 12|0 --jpeg --colour` and `uv run python scripts/score_sim_detections.py <dir>`.
  Shipped pass, people found/in view (Cesium Man of #111 → rigged CC0): efficientdet 7→20/113,
  ssd-mobilenet 15→27/113, ssdlite 38→65/113. `earthquake-survivors` whole loop, ssdlite: standing
  18/66, sitting 18/38, waving 0/33, lying 0/6 (other profiles lower). Full table and iterations in
  `docs/simulation/bevy-simulation.md` § *On-board detectors (measured)*.

## Prerequisites

Deferred-work scan: `2026-11-03-bevy-visual-checkpoints-v3-v5.md` — ℹ unrelated. Nothing blocks.

## Decisions & Trade-offs

- **Orchestrator decisions (2026-11-04), recorded as deferred answers:** one humanoid concept
  (`2026-11-04-one-humanoid-model-concept.md`: n2's rig merged into main's `FigureModel`, main's
  names win; the shipped-figure assertion of #111 was never Cesium-specific, so no main test
  changed beyond `rig: None` in literals) and two CC0 models shipped with Cesium Man's pin dropped
  (`2026-11-04-two-cc0-people-and-cesium-man-dropped.md`).
- **Detector cross-check (developer, 2026-11-04):** people are scored per pose; a lying person's
  truth box is horizontal; only the shirt wears the hi-vis coat (whole-body tint found people
  less); the preset's survivors stand on open ground, as the scene does not test occlusion.

- Players are seeked to simulation time instead of advanced by Bevy's clock: stills and
  recordings must replay; costs a seek per figure per frame (tens of figures — negligible).
- The capsule figure stays as the fallback: CI and asset-less checkouts render people, and a
  scenario never breaks because a download failed.
- One rig for everyone, varied by height, coat and phase, rather than a character library: one
  pinned asset; per-person `glb` override is the escape hatch.
- Stylised CC0 characters over photo-real scans: the pinned-CC0 rule wins.
- A posed person is tracked in `object_tracks.jsonl` even without a tree (`Figure::posed`): a
  survivor lying still is exactly the truth a survey is judged on.
- `FigureDef` is no longer `Copy` (the rig holds strings); callers clone or borrow.
- **Requirement change (developer, 2026-11-04, option b): "ship two models: one for sitting, one
  for waving".** No CC0 human on Poly Pizza carries both a sit clip and a wave clip, so the figure
  ships two pinned models instead of one rig with every clip. The requirement becomes *every pose
  has a clip across the primary rig and its pose overrides*: each pose resolves to a clip the
  primary `rig` or its `pose_rigs` entry names, and that clip is an animation of a pinned CC0 file.
  Still required: `idle`, `walk` and `run` on every rig. `wave`, `sit` and `lie` become optional
  in `clips` (a rig names the poses it carries). Test `the_shipped_figure_is_rigged_with_every_clip`
  is replaced by `the_shipped_figure_has_a_clip_for_every_pose_in_a_pinned_file`; it reads each
  file's animation names from `assets/assets.lock.json` (`animations`), because CI does not fetch
  models and must check the same clips.
