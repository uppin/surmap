# Changeset: behaviour trees for simulation objects and the wind

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — a pure, deterministic behaviour-tree runtime in Rust plus moving bodies in the
renderer, Python validation/edits/tools/proto and capture ground truth; one small visual checkpoint

PRD: `PRD-2026-11-03-sim-behaviour-trees.md` · Discovery:
`2026-11-03-sim-behaviour-trees-initial-discovery.md` · Visual spec:
`2026-11-03-sim-behaviour-trees-visual-spec.md`

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery, visual spec · these files (`/yolo-pr-stack` pass 2)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7)
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · Rust 17 red (`behaviour.rs` stubs, incl. burning areas, manifest validation, golden); Python 16 red (`behaviour_of`/`set_behaviour`/`update_behaviour_node`, proto `SetBehaviour…`/`skin`, `object_tracks`, preset, golden) — tool tests stop first on n3's `wildfire-edge` preset (inherited, green in n3)
  - [x] Acceptance tests written and failing for the right reason (`tests/test_sim_behaviour_e2e.py`)
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Rust `behaviour.rs`: parse, validate per target, deterministic tick (contract below)
  - [ ] Rust `scene_manifest.rs`: `behaviour` on `person` elements and on `weather.wind`, validated per target (`WindDef` is no longer `Copy` — n3 code that copied it clones)
  - [ ] Rust runtime: people move by their trees at the fixed tick; the wind tree drives `WindModel` (and so Feronia, the fire's spread, flame lean and smoke drift from n3); figures turn to their heading and bob while moving, per the visual spec
  - [ ] Recorder: `object_tracks.jsonl` beside every capture (contract below)
  - [ ] Python `scenario_manifest`: `validate_behaviour`, pure edits `set_behaviour`, `update_behaviour_node`, `behaviour_of`; preset `wildfire-evacuation`
  - [ ] `SimulationTools`: `SetBehaviour`, `UpdateBehaviourNode`, `GetBehaviour`; `PersonElement` gains `skin`; regenerated code, handlers, docs table
  - [ ] `bevy_capture`: `load_bevy_capture(...).object_tracks` and `.wind`
  - [ ] Gates green; `cargo test --locked`; `cargo check --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (tests + the planner-reviewed B1 screenshot set)
  - [ ] `docs/simulation/bevy-simulation.md` — Behaviour trees; `docs/agent.md` — the three tools
  - [ ] `docs/simulation/changelog/2026-11-03-sim-behaviour-trees.md`
  - [ ] Lint (`--no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Stack Context

Stack slug `sim-disaster-2`: `main ← n3 feat/sim-weather-wildfire ← n4 feat/sim-behaviour-trees (this) ← sweep`.

### Green wave

**Wave:** 2 of 2 · **Node:** n4 · **Concurrent with:** none · **Blocks:** nothing ·
**Needs:** n3 (#100) — `WindModel`, `FireSpec::burnt`/`perimeter`, `weather.wind`, the
`wildfire-edge` preset and `fire_perimeter.jsonl` are the behaviour this node reads.
**Greenable independently?** no — waits on n3's Green row.

### Inherited Dependencies — do not implement here

n3's wind and fire models, manifest `weather`/`fires`/`vegetation`, its tools and presets. This
node only reads them; a gap found there is reported, not patched here.

## Background

The developer (2026-11-03): "we should also let the agent define and change behaviour trees for the
objects in the simulation"; "let's also add wind (behaviour tree driven) and trees reacting to the
wind"; "of course, everything should come declarative".

## State A (before, after n3)

People stand still; the wind is one constant (plus gusts) from `weather.wind`.

## State B (after)

### Behaviour-tree JSON (inline in the manifest — no rebuild, no code)

Every node is an object with `"node"` naming its kind and an optional `"id"` (unique within its
tree; the address `update_behaviour_node` edits by):

| Node | Fields | Ticks to |
|---|---|---|
| `sequence` | `children` | first non-success child's status; success when all succeed |
| `selector` | `children` | first non-failure child's status; failure when all fail |
| `parallel` | `children`, `succeed_on` `all` \| `one` | runs every child each tick |
| `repeat` | `child`, `times` (omitted = forever) | restarts the child on success |
| `invert` | `child` | swaps success and failure |
| `time_after` | `s` | success once sim time ≥ `s`, else failure |
| `near_fire` | `within_m` | success when any burning perimeter is within `within_m` |
| `near_object` | `id`, `within_m` | success when that object is within `within_m` |
| `wind_above` | `speed_m_s` | success when the current wind speed exceeds it |
| `idle` | `s` | running for `s` seconds, then success |
| `move_to` | `enu` `[e, n]`, `speed_m_s` | running until within 0.25 m, then success |
| `follow_path` | `enu` `[[e, n], …]`, `speed_m_s` | `move_to` each point in turn |
| `wander` | `radius_m`, `speed_m_s`, `seed` | never ends; seeded points around where it started |
| `flee_from_fire` | `speed_m_s`, `clearance_m` | away from the nearest perimeter point; success at `clearance_m` |
| `set_wind` | `from_deg`, `speed_m_s`, `gust_m_s`, `over_s` | ramps the wind linearly to these (shortest way round the compass); success when reached |

- **Targets.** `person` elements take `"behaviour": <node>`; the scenario's wind takes
  `weather.wind.behaviour`. Object trees may not use `set_wind`; the wind's tree may use only
  composites, decorators, `time_after`, `idle` and `set_wind`.
- **Tick.** Fixed 10 Hz in simulation time, on the renderer's `SimTime`, so a recording replays
  identically (same seeds, same tracks). Bodies move on the ground plane at `speed_m_s`; `up` is
  the ground.
- **Runtime (`behaviour.rs`, pure):** `Tree::from_json(&str) -> Result<Tree, String>`,
  `Tree::validate(Target::{Object, Wind})`, `Runner::new(tree, position: Vec2, wind: WindModel)`,
  `Runner::tick(&mut self, &World, dt) -> Status::{Running, Success, Failure}`, `runner.position`,
  `runner.wind`, `runner.action() -> Option<&str>` (the running leaf's kind). `World { t_s,
  fires: &[FireSpec], burning_areas: &[Vec<Vec2>], wind: &WindModel, objects: &[(String, Vec2)] }`
  — `burning_areas` is other burning ground (n5's burning buildings' footprints), which `near_fire`
  and `flee_from_fire` treat like a wildfire perimeter; this node passes it empty. A root that finishes is
  not restarted (wrap it in `repeat`).
- **Scope.** Moving people are layered ground truth for the survey, never written into the static
  scene or RTAB-Map's map (`docs/architecture.md` §1). Nothing here controls the drone.

### Ground truth

`object_tracks.jsonl` per capture, one line per frame:
`{"t_ns": n, "wind_enu": [ve, vn], "objects": [{"id": "evacuee-1", "enu": [e, n, u], "action": "flee_from_fire"}]}`;
`load_bevy_capture(dir).object_tracks: dict[int, dict[str, Vec3]]` and
`.wind: dict[int, tuple[float, float]]` (by `t_ns`; both empty when the file is absent).

### Tools

| Tool | Does | Execution |
|---|---|---|
| `set_behaviour` | a target's (`person` id, or `wind`) whole tree, as JSON | SYNC · 10 s · FAIL |
| `update_behaviour_node` | replaces the node with that `id` in a target's tree | SYNC · 10 s · FAIL |
| `get_behaviour` | a target's tree as JSON | SYNC · 10 s · FAIL |

An invalid tree, an unknown target or node id → `INVALID_ARGUMENT`; each edit is a new scenario
version. `PersonElement` gains `skin` (the renderer always needed one; `add_element` defaulted it).

Preset `wildfire-evacuation` — `wildfire-edge` plus three people at the stand's downwind edge,
each `selector[ sequence[near_fire 20 m, flee_from_fire 3 m/s 30 m], wander 6 m 0.8 m/s ]`, and a
wind tree `sequence[ idle 20 s, set_wind 300° 10 m/s gust 3 over 30 s ]`.

## Verification

- **V1** — Rust: `behaviour.rs` tests (each node kind, determinism, a fleeing person never inside
  the burnt area over 120 s, the wind ramp), manifest tests incl. the golden
  `tests/fixtures/sim_scenario/wildfire-evacuation.json`; Python: validation, edits, preset, tools,
  capture tracks, the agent-turn acceptance test.
- **V4** (consented: planner reviews screenshots against the spec) — B1 checkpoints.

## Prerequisites

Deferred-work scan: the 2026-11-03 Bevy records are ℹ unrelated; n3's open TODOs are n3's.

## Decisions & Trade-offs

- Inline JSON trees rather than node files: one manifest is the whole scenario the store versions;
  reuse is the agent copying a tree.
- A hand-rolled runtime (~300 lines, pure) over a crate: the node set is small, determinism and
  wasm are required, and the tree must be the manifest's JSON, not a crate's format.
- The wind is a target like a person, so "wind driven by a behaviour tree" needs no second
  mechanism; n3's single `WindModel` then carries the change to vegetation, fire and particles.
