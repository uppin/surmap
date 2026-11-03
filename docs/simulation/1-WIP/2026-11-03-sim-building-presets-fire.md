# Changeset: building wall/roof/district presets on Overture's vocabulary, and building fires

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — Rust (preset resolution, a floor-by-floor fire with spread between buildings and
from the wildfire, curtain-wall and roof-shape geometry, fire effects) and Python (validation,
edits, tools, proto, capture), 25 texture presets, visual work judged by screenshots

PRD: `PRD-2026-11-03-sim-building-presets-fire.md` · Discovery:
`2026-11-03-sim-building-presets-fire-initial-discovery.md` · Visual spec:
`2026-11-03-sim-building-presets-fire-visual-spec.md`

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery, visual spec · these files (`/add-to-pr-stack`)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7)
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · Rust 22 red (`building_style.rs`, `building_fire.rs` stubs, unshipped presets, manifest rules, golden); Python 33 red (presets/edits/validation, proto `StyleBuilding…`, `building_fires`, presets, golden, served files)
  - [x] Acceptance tests written and failing for the right reason (`tests/test_sim_building_fire_e2e.py`)
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Rust `building_style.rs`: facade, roof, district preset loaders and validation; deterministic weighted resolution (contract below)
  - [ ] Rust `building_fire.rs`: floor-by-floor fire, spread between buildings and from the wildfire (contract below); burning footprints into n4's `World.burning_areas`
  - [ ] Rust `scene_manifest.rs`: `districts`, `building_fires`, building `facade`/`roof`/colours/`roof_shape`/`floors`/`glazing`; `material` optional when a preset resolves
  - [ ] Declarative assets — every value the visual spec names, none in Rust: 11 `building/facades/*.facade.json`, 14 `building/roofs/*.roof.json`, 4 `building/districts/*.district.json`, `building/fire.json`, `fx/window_flames.fx.json`, `fx/building_smoke.fx.json`; CC0 textures added to `assets.lock.json` through the licence-gated sources
  - [ ] Rendering per the visual spec: textured walls and roofs, roof shapes, punched windows and curtain walls, per-floor fire (window flames, smoke, interior glow, broken panes, charring), a screenshot set at each checkpoint
  - [ ] Recorder: `building_fires.jsonl` beside every capture
  - [ ] Python `scenario_manifest`: validation; `building_presets`, `set_district`, `remove_district`, `style_building`, `add_building_fire`, `remove_building_fire`; presets `district-showcase`, `downtown-blaze`
  - [ ] `SimulationTools`: `ListBuildingPresets`, `SetDistrict`, `RemoveDistrict`, `StyleBuilding`, `AddBuildingFire`, `RemoveBuildingFire`; regenerated code, handlers, docs table
  - [ ] `bevy_capture`: `load_bevy_capture(...).building_fires`
  - [ ] Gates green; `cargo test --locked`; `cargo check --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (tests + the planner-reviewed D1–D2 screenshot sets)
  - [ ] `docs/simulation/bevy-simulation.md` — Buildings and building fires; `docs/agent.md` — the tools
  - [ ] `docs/simulation/changelog/2026-11-03-sim-building-presets-fire.md`
  - [ ] `HACKATHON.md` — texture sources rows
  - [ ] Lint (`--no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Stack Context

Stack slug `sim-disaster-2`: `main ← n3 #100 ← n4 #101 ← n5 feat/sim-building-presets-fire (this) ← sweep`.

### Green wave

**Wave:** 3 of 3 · **Node:** n5 · **Concurrent with:** none · **Blocks:** nothing ·
**Needs:** n3 (#100) — `FireSpec`, the fx loader and emitters, `WindModel`; n4 (#101) — `World.burning_areas`
(burning buildings make people flee) and the wind tree changing spread.
**Greenable independently?** no — waits on n4's Green row (and so n3's).

### Inherited Dependencies — do not implement here

n3's wildfire, wind, fx definitions and emitters; n4's behaviour runtime. Read, never patched here.

## Background

The developer (2026-11-03): presets for building textures on the vocabulary Meta's map data
provides — answered as **Overture's building attributes** (`overture-buildings` in
`src/surmap/agent/tools/map_layers.py`; no geometry import); the agent decides which preset a
district uses, individual buildings may differ, walls and roofs separately, windows and glass
cladding considered; building fires simulated — answered **floor by floor, spreading between
buildings and from the wildfire**; "those should also come declarative".

## State A (before)

`building` is one cuboid with one manifest material and an optional punched window grid; flat
top; nothing burns but n3's ground fire.

## State B (after)

### Everything is runtime JSON

| File | Holds |
|---|---|
| `building/facades/<name>.facade.json` | `material` (a manifest material definition: textures, `uv_scale`, roughness…), `colourable` (whether a colour tints it), `glazing` default `{kind: punched \| curtain_wall \| none, window_ratio, pane_m, bay_m, glass, frame}` (`curtain_wall`: `mullion_m [w, h]`, `mullion`), `burnt` material |
| `building/roofs/<name>.roof.json` | `material`, `colourable`, `burnt` |
| `building/districts/<name>.district.json` | weighted `facades`, `roofs`, `roof_shapes` (`[[name, weight], …]`), `facade_colours` / `roof_colours` palettes, `floor_m` |
| `building/fire.json` | `climb_s_per_floor`, `descend_factor`, `floor_burn_s`, `ignite_distance_m`, `ignite_wind_gain_s` (extra metres downwind per m/s), `exposure_s`, `effects` `{window_flames, smoke, embers}` fx paths, glow colour/intensity |

Shipped names are Overture's: facades `brick, cement_block, clay, concrete, glass, metal, plaster,
plastic, stone, timber, wood`; roofs `concrete, copper, eternit, glass, grass, gravel, metal,
plastic, roof_tiles, slate, solar_panels, tar_paper, thatch, wood`; districts `old-town, downtown,
industrial, suburban`. A **name** (no `/`) means the shipped file of that kind; a **path**
(`building/facades/my-red.facade.json`) names any other file — a new preset is a new file.

### Manifest

```json
"districts": [{"id": "core", "preset": "downtown", "position_enu": [0, 0, 0], "size_m": [120, 80], "seed": 4}],
"elements": [{"kind": "building", "id": "tower-2", "size_m": [18, 18, 42], "position_enu": [30, 10, 0],
              "facade": "glass", "roof": "metal", "roof_shape": "flat", "floors": 12,
              "facade_colour": [0.55, 0.6, 0.65], "glazing": {"kind": "curtain_wall"}}],
"building_fires": [{"id": "blaze-1", "building": "tower-2", "floor": 3, "start_s": 5}]
```

- **Resolution** of each building's facade, roof, roof shape, colours, glazing and floors: the
  building's own field › the district whose rectangle holds the building's centre (later districts
  win overlaps), drawn by weight from a hash of `(district seed, building id)` › the legacy
  `material` / `windows` › refused. `floors` default `floor(height / floor_m)`.
- `roof_shape` `flat | gabled | hipped | pyramidal` (Overture's others → refused; the agent maps
  them). `glass` facades default to `curtain_wall`.
- `building_fires`: `building` an existing building id, `0 ≤ floor < floors`, `start_s ≥ 0`,
  `tuning` (default `building/fire.json`) — ids unique with every other id.

### Building fire model (`building_fire.rs`, pure, stepped)

`BuildingFires::new(buildings: Vec<Footprint { id, polygon_enu, floors }>, ignitions, tuning)`;
`step(&mut self, t_s, dt, wind_enu: Vec2, wildfires: &[FireSpec])`; `floor(id, f) ->
FloorState::{Intact, Burning, Burnt}`; `ignited_at(id) -> Option<f32>`;
`burning_footprints() -> Vec<Vec<Vec2>>`.

- From ignition floor `f₀` at `t₀`: floor `f` ignites at `t₀ + (f − f₀)·climb` above, `t₀ + (f₀ −
  f)·climb·descend_factor` below; burns `floor_burn_s`, then `Burnt`.
- Spread: building B ignites (at the floor nearest the source's lowest burning floor) when
  a burning building's footprint is within `ignite_distance_m + ignite_wind_gain_s · max(0, U·d̂)`
  of B's (d̂ the unit direction source → B) for `exposure_s` continuously.
- A wildfire's burnt area touching B's footprint ignites B's floor 0 at that time.
- Deterministic for the same inputs and `dt`.

### Ground truth

`building_fires.jsonl`: `{"t_ns": n, "buildings": [{"id": "tower-2", "burning": [3, 4], "burnt": [2]}]}`;
`load_bevy_capture(dir).building_fires: dict[int, dict[str, tuple[tuple[int, ...], tuple[int, ...]]]]`
(`(burning, burnt)` by `t_ns`; empty when absent).

### Tools

| Tool | Does | Execution |
|---|---|---|
| `list_building_presets` | facade, roof and district names (shipped and any added files) | SYNC · 10 s · FAIL |
| `set_district` | a district: id, preset, rectangle, seed (replaces one with that id) | SYNC · 10 s · FAIL |
| `remove_district` | by id | SYNC · 10 s · FAIL |
| `style_building` | one building's facade, roof, roof shape, colours, floors, glazing (unset = from district) | SYNC · 10 s · FAIL |
| `add_building_fire` | id, building, floor, start | SYNC · 10 s · FAIL |
| `remove_building_fire` | by id | SYNC · 10 s · FAIL |

Presets: `district-showcase` — four districts side by side on the empty lot, six generic buildings
each, no fire (the look checkpoint); `downtown-blaze` — a downtown block of eight buildings incl. a
glass tower, a 5 m/s westerly, a fire on the tower's floor 3 at t = 5 s and a neighbour 5 m
downwind.

## Verification

- **V1** — Rust: `building_style.rs`, `building_fire.rs`, manifest tests incl. the golden
  `tests/fixtures/sim_scenario/downtown-blaze.json`; Python: validation, edits, presets, tools,
  capture, the agent-turn acceptance test.
- **V4** (developer consented: planner-reviewed screenshots) — D1 and D2 checkpoints.

## Prerequisites

Deferred-work scan (`src/surmap/docs/todo/`, `code-issues/`, deferred answers): the 2026-11-03 Bevy
records (`bevy-visual-checkpoints-v3-v5`, `camera-profile-fisheye-and-render-tests`,
`sidecar-odometry-covariance`, `bevy-loop-closure-acceptance`, `bevy-live-websocket-stream`) are
ℹ unrelated; nothing the PRs below deferred becomes actionable here.

## Decisions & Trade-offs

- Overture's vocabulary as preset names: the station's own map layer speaks it, so a later import
  can map attributes one-to-one; no import in this PR (developer's answer).
- Presets are files, names are sugar: a district or facade the agent wants that is not shipped is a
  JSON file, never code.
- `building_fires` separate from n3's `fires`: n3's ground fire stays untouched; both reach
  people through n4's `burning_areas`.
