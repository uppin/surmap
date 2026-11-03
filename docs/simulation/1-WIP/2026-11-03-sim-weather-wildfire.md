# Changeset: weather, wind-swept vegetation and an animated wildfire in the Bevy simulation

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — Rust (Bevy rendering with a new GPU-particle dependency, pure spread and wind
models, Feronia vegetation) and Python (store, tools, capture), visual work judged by screenshots

PRD: `PRD-2026-11-03-sim-weather-wildfire.md` · Discovery:
`2026-11-03-sim-weather-wildfire-initial-discovery.md` · Visual spec:
`2026-11-03-sim-weather-wildfire-visual-spec.md`

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery, visual spec · these files (`/yolo-pr-stack` pass 2)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7)
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · Python 12 red (missing edits, proto messages, presets, `fire_perimeters`, served fx/species), Rust 20 red (`todo!()` models, loaders, manifest rules, golden); existing suites green
  - [x] Acceptance tests written and failing for the right reason (`tests/test_sim_wildfire_e2e.py`)
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ✅ 2026-11-03 `/green` Green — implement until every red test passes · Python 1855 green (was 12 red), Rust 86 green (was 20 red); wasm32 `cargo check` green, nothing gated off; W1-W3 screenshot sets in scratchpad `n3-shots/`
  - [x] Rust `scene_manifest.rs`: `weather`, `fires`, element kind `vegetation` (contract below); the shipped `scene.json` stays valid
  - [x] Rust `wind.rs` and `fire.rs`: the pure wind and fire-spread models (contract below)
  - [x] Declarative assets: `fx/*.fx.json` and `species/*.species.json` loaders and validation (Rust + Python); the shipped files carry the visual spec's values; no visual constant left in Rust
  - [x] Rust rendering, exactly per the visual spec: `bevy_hanabi = "0.18"` (consented dependency) flames, embers, smoke, rain; burnt ground behind the front; Feronia-wind pines and grass ported from the developer's FeroniaDemo (`~/Code/FeroniaDemo/src/{meshes,forest,main}.rs`); `GlobalWind` driven by `weather.wind`; flames lean and smoke bends with the same wind — a screenshot set at each visual checkpoint (`--screenshot <dir> --at <t> --scenario <id>`)
  - [x] Recorder: `fire_perimeter.jsonl` beside every capture (one line per frame: `t_ns`, fires with their ENU perimeter)
  - [x] Python `scenario_manifest`: validate `weather`, `fires`, `vegetation`; pure edits `set_weather`, `add_fire`, `remove_fire`; presets `wildfire-edge`, `flood-street`
  - [x] `SimulationTools`: `SetWeather`, `AddFire`, `RemoveFire` rpcs, regenerated code, handlers, docs table
  - [x] `bevy_capture`: `load_bevy_capture(...).fire_perimeters`
  - [x] Gates green; `cargo test --locked`; `cargo check --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (tests + the planner-reviewed screenshot sets)
  - [ ] `docs/simulation/bevy-simulation.md` — Weather, wind and fire; `docs/agent.md` — the three tools
  - [ ] `docs/simulation/changelog/2026-11-03-sim-weather-wildfire.md`
  - [ ] `HACKATHON.md` — `bevy_hanabi`, `bevy_eidolon` rows
  - [ ] Lint (`--no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Stack Context

Stack slug `sim-disaster-2`: `main ← n3 feat/sim-weather-wildfire (this) ← n4 feat/sim-behaviour-trees ← sweep`.

### Green wave

**Wave:** 1 of 2 · **Node:** n3 · **Concurrent with:** none · **Blocks:** n4 (behaviour trees read
the live fire and drive the wind) · **Needs:** nothing unmerged (#89, #91 on `main`).
**Greenable independently?** yes.

## Background

The developer's interview (2026-11-03, accepted): weather and an animated wildfire; wind, with trees
reacting to it and the fire reacting to it ("also fire reacting to wind"); `bevy_hanabi` 0.18
consented; visuals verified by planner-reviewed screenshots against a spec. Reference for wind-swept
pines and grass: the developer's own Bevy 0.18 / Feronia 0.8.4 demo built with Codex
(`~/Code/FeroniaDemo`, copied from `~/Documents/ChatGPT/FeroniaDemo`).

## State A (before)

No weather, fire or vegetation in the scenario manifest; one static `ClearColor`-free HDRI sky and
haze; the Feronia debris scatter has `WindAffected` but nothing drives `GlobalWind`.

## State B (after)

### Manifest additions (`scene_manifest.rs`, mirrored in `scenario_manifest.py`)

```json
"weather": {"rain_mm_h": 0.0, "fog_visibility_m": 450.0,
            "wind": {"from_deg": 250.0, "speed_m_s": 6.0, "gust_m_s": 2.0}},
"fires": [{"id": "front-1", "ignition_enu": [-20.0, 60.0, 0.0], "start_s": 2.0,
           "spread_m_s": 0.15, "max_radius_m": 35.0, "smoke": true}],
"elements": [... {"kind": "vegetation", "id": "pines-west", "species": "pine",
                  "position_enu": [-40.0, 60.0, 0.0], "size_m": [40.0, 60.0],
                  "density_per_100m2": 3.0, "seed": 11} ...]
```

- `weather` optional; `rain_mm_h` ≥ 0 (default 0); `fog_visibility_m` > 0 overrides
  `environment.fog_visibility_m`; `wind.from_deg` is meteorological (where it blows **from**,
  clockwise from north), `speed_m_s` ≥ 0, `gust_m_s` ≥ 0 (defaults 0).
- `fires` optional list; ids unique across elements, models and fires; `spread_m_s` > 0,
  `max_radius_m` > 0, `start_s` ≥ 0, `smoke` default true.
- `vegetation` element: `species` `pine` | `grass`, `size_m` (east, north) > 0,
  `density_per_100m2` in (0, 50], `seed`.

### Everything tunable is runtime JSON (developer, 2026-11-03: "everything should come declarative")

Rust implements only the *kinds* — a particle emitter, the procedural pine and grass generators,
the ellipse spread model. Every number the visual spec names ships as JSON under `assets/` and is
loaded at runtime like the scene (no rebuild to tune):

- `fx/<name>.fx.json` — a particle effect: `colour_gradient` (`[[t, [r, g, b], intensity, alpha], …]`),
  `size_m` `[start, end]`, `lifetime_s` `[min, max]`, `velocity_m_s` `[x_up, …]` as `{"up": …,
  "wind_coupling": …, "gravity": …}`, `blend` (`additive` | `alpha`), `spawn` (`per_metre` or
  `per_second`), `max_particles`. Shipped: `flames`, `embers`, `smoke`, `rain`.
- `species/<name>.species.json` — vegetation: `generator` (`pine` | `grass`), `palette` (sRGB
  stops), `height_m` `[min, max]`, `wind_damping` (Feronia `strength`, `micro_strength`,
  `s_curve_strength`, `bop_strength`, `twist_strength` multipliers), `lod_distance_m`,
  `burnt_palette`. Shipped: `pine`, `dry_grass`.
- A fire names its effects (`"effects": {"flames": "fx/flames.fx.json", …}`, defaults the shipped
  ones) and may override the model's coefficients (`"head_wind_gain": 0.5, "lb_wind_gain": 0.25`).
- `weather` names its rain effect (`"rain_fx": "fx/rain.fx.json"`) and the wet-surface factors
  (`"wet_roughness": 0.6, "wet_darkening": 0.85`).
- The manifest validator (Rust and Python) checks every referenced path is relative and every file
  kind; the store's `/sim/assets/` serving covers them like any other asset.

### Wind model (`wind.rs`)

`WindModel::from(&Wind)`; `velocity_enu(t_s) -> Vec2` is the vector the air moves **toward**
(from_deg 270 → +east); speed `speed_m_s + gust_m_s * sin(2π t / 7 s + phase)` with `phase` fixed per
scenario (0); `feronia(&self, t_s) -> bevy_feronia::prelude::Wind`: direction = the Bevy xz unit
vector of `velocity_enu` (east → +x, north → −z), `strength = clamp(speed / 15, 0, 1)`.

### Fire model (`fire.rs`) — Huygens ellipse, rear focus at ignition

With burning time τ = t − start_s (no fire while τ < 0), wind speed U (m/s) toward unit `d`:
head rate `R = spread_m_s · (1 + head_wind_gain · U)`, length-to-breadth `LB = 1 + lb_wind_gain · U`
(gains from the fire, defaults 0.5 and 0.25), back rate
`R_b = R (LB − √(LB² − 1)) / (LB + √(LB² − 1))`; semi-major `a = (R + R_b) τ / 2`, semi-minor
`b = a / LB`, the ellipse's centre at `ignition + d (a − R_b τ)`. Every axis is capped so no point
of the perimeter is farther than `max_radius_m` from ignition. `FireFront::perimeter(t, wind,
points=48) -> Vec<[f32; 2]>` (ENU, counter-clockwise, closed implicitly); `burning(p, t, wind)`;
`burnt(p, t, wind)` (inside the perimeter). Zero wind → a circle of radius `spread_m_s · τ`.

### Ground truth

`fire_perimeter.jsonl` per capture: `{"t_ns": n, "fires": [{"id": "front-1", "polygon_enu": [[x, y], …]}]}`;
`load_bevy_capture(dir).fire_perimeters: dict[int, dict[str, tuple[tuple[float, float], ...]]]`
(by `t_ns`, empty when the file is absent).

### Tools

| Tool | Does | Execution |
|---|---|---|
| `set_weather` | rain, fog visibility, wind (from, speed, gust) | SYNC · 10 s · FAIL |
| `add_fire` | id, ignition ENU, start, spread, max radius, smoke | SYNC · 10 s · FAIL |
| `remove_fire` | by id | SYNC · 10 s · FAIL |

Presets: `wildfire-edge` — the empty lot with two pine stands, grass, a westerly 6 m/s wind and one
fire at the stand's upwind edge; `flood-street` — the earthquake block with 8 mm/h rain, fog
visibility 250 m, calm 2 m/s wind.

## Verification

- **V1** — Rust: `wind.rs`, `fire.rs`, manifest tests; Python: manifest edits, presets, tools,
  capture perimeters; a golden `wildfire-edge` scenario written by the store parsed by the
  renderer's tests (`tests/fixtures/sim_scenario/wildfire-edge.json`).
- **V4** (consented in the interview: planner reviews the screenshots against the spec) — the
  visual-spec checkpoints on `wildfire-edge` at t = 5, 40, 120 s and `flood-street` at t = 20 s.

## Prerequisites

Deferred-work scan: the 2026-11-03 Bevy records (`bevy-visual-checkpoints-v3-v5`,
`camera-profile-fisheye-and-render-tests`, `sidecar-odometry-covariance`,
`bevy-loop-closure-acceptance`, `bevy-live-websocket-stream`) are ℹ unrelated to this node's scope.

## Decisions & Trade-offs

- Green additions the contract left open (all runtime JSON, none in Rust): fx files also carry
  `round` (ellipse particles), `stretch` (rain streak length over width), `box_m`, `emitter_spacing_m`
  and `refresh_s`; `flames.fx.json` carries the fire's `ground` (scorch + glowing rim) and `light`;
  `spawn.per_mm_h` scales rain with `rain_mm_h`; species carry `plants_per_unit` (grass clumps per
  density unit; Feronia scatters `density²` instances over a stand, so the renderer passes
  `√clumps`); `weather.wet_materials` names the surfaces that look wet (default ground, asphalt).
- Feronia collects a scatter root's assets only in its global Setup to Collecting pass, so sowing
  grass sets `ScatterState::Setup` again and scatters once the state is `Ready`.
- Native review stills of a scene with fires aim the overview camera at the first ignition (from
  its south, raised); without fires the overview is unchanged.
- `fire_perimeter.jsonl` is written only when the scene has fires (absent otherwise, which the
  loader reads as no perimeters).

- One wind for everything: the manifest's `weather.wind` drives Feronia's `GlobalWind`, the fire
  ellipse, flame lean and the smoke/rain/ember forces. n4 makes it change over time.
- Vegetation is procedural (FeroniaDemo's pine and grass meshes): no external assets, so adding
  a stand is a JSON edit.
- New dependencies (consented): `bevy_hanabi = "0.18"`, and `bevy_eidolon = "0.4"` (Feronia's
  instancing companion, used by the demo's grass).
