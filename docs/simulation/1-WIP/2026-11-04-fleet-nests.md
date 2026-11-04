# Changeset: drone nests the agent places, and the simulation-only fleet exception

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — two languages (Rust manifest + renderer, Python mirror + agent handler), a
proto contract change (`AddElementRequest` oneof field 8), cross-element geometry rules; plus the
scope amendment across four documents

PRD: `PRD-2026-11-04-fleet-nests.md` · Discovery: `2026-11-04-fleet-nests-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-pr-stack` Plan — PRD, changeset, initial discovery · these files (`/plan-pr-stack` pass 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Build and baseline healthy (`uv run mypy`, `uv run pytest -q`, `cargo test --locked`)
  - [ ] Stubs this node owns (`DroneNest`, `Element::DroneNest`, `scene_manifest/fleet.rs`, `simulation/fleet_nests.py`, proto `DroneNestElement`)
  - [ ] Acceptance tests written and failing for the right reason
  - [ ] Unit/integration tests written and failing
  - [ ] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes (`[G]` on Sonnet only — see Stack Context) ·
  - [ ] Rust `scene_manifest.rs`: `Element::DroneNest(DroneNest)`, arms in `id()` / `materials()`; `scene_manifest/fleet.rs` `validate_nests()` called from `from_json`; `DroneNest::drone_ids()`
  - [ ] Rust `world.rs`: `Builder::nest` spawns the pad (rim, deck, "H"), a `NestPad { id }` component, and the `Nests` resource (id, ENU pad centre, yaw, drone ids)
  - [ ] Python `simulation/fleet_nests.py`: `validate_nests(manifest)`, `nests_of(manifest) -> tuple[Nest, ...]`; `scenario_manifest.py` `ELEMENT_KINDS` + `validate_manifest` + `element_ids` include nest drone ids
  - [ ] Python `water.py`: `water_surfaces(manifest)` public (today's private `_Surface`), reused by nests and vessels
  - [ ] Preset `earthquake-fleet` (3 nests, 5 drones) in `load_presets`; golden `tests/fixtures/sim_scenario/fleet-nests.json`, parsed by Rust
  - [ ] Proto `DroneNestElement` (`AddElementRequest.drone_nest = 8`); `scripts/gen_agent_rpc.py` regenerated; `_element()` handler arm
  - [ ] `skills/building-a-simulation-scene/SKILL.md`: when and how to place nests
  - [ ] Scope amendment: `docs/architecture.md` §1 table + text, §2.3, §4.3; `AGENTS.md` scope guardrail; `README.md:17-20`; `flight.rs:3` doc comment
  - [ ] Gates green; `cargo test --locked`; `cargo check --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (tests + a native still of `earthquake-fleet` showing the three pads)
  - [ ] `docs/simulation/bevy-simulation.md` — *Drone nests* section (element table, placement rules, the pad)
  - [ ] `docs/agent.md` — `drone_nest` element fields under `add_element`
  - [ ] `docs/simulation/changelog/2026-11-04-fleet-nests.md`
  - [ ] Validate tests (`/validate-tests`)
  - [ ] Lint (`ruff --no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-04-fleet-nests-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Stack Context

**Stack**: drone nests and an agent-tasked simulated fleet · slug **`#drone-fleet`** — this PR is
**1 of 5** · `#pending`
**Branch**: `pr-1-drone-fleet` · **Base**: `origin/main`
**Successor**: `pr-2-drone-fleet`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = `/plan-red` Steps 7–9 (stubs, failing acceptance + unit tests)
**Workflow override**: `[G]` (the Green row) runs on **Sonnet only**, instead of the
`/yolo-pr-stack` rubric's Haiku column. Effort comes from this node's complexity: 1–2 low,
3 medium, 4–5 high. A `[G]` retry stays on Sonnet, one effort step up, and never goes to Opus.
`[W]`/`[F]` keep the default rubric. Approved by the developer, 2026-11-04, for the whole
`#drone-fleet` stack. See `## Decisions & Trade-offs`.

Why the boundary falls here: the nest is scene data, the one fact every later node needs (the
autopilot docks drones on it, the controller validates drone ids against it). It touches only the
manifest seam, so it can merge alone. It carries the scope amendment because it is the bottom
node, so the amendment lands before any code that flies a drone.

### Owned API surface

- Rust: `scene_manifest::DroneNest` (`id`, `position_enu`, `yaw_deg`, `drones`),
  `Element::DroneNest`, `DroneNest::drone_ids()`, `scene_manifest/fleet.rs` (`validate_nests`,
  constants `NEST_PAD_M = 2.4`, `NEST_SPACING_M = 6.0`, `MAX_NESTS = 8`,
  `MAX_DRONES_PER_NEST = 4`, `NEST_BOUND_M = 500.0`, `NEST_MAX_UP_M = 60.0`); `world::Builder::nest`,
  `NestPad { id }`, `Nests` resource (`Nest { id, pad_enu: [f32; 3], yaw_deg, drone_ids }`).
- Python: `surmap.simulation.fleet_nests` (`Nest`, `validate_nests`, `nests_of`), `water.water_surfaces`,
  preset `earthquake-fleet`, `ELEMENT_KINDS += "drone_nest"`.
- Proto: `DroneNestElement`, `AddElementRequest.drone_nest = 8`; handler arm in `simulation_handlers._element`.
- Docs: the scope amendment text in `docs/architecture.md`, `AGENTS.md`, `README.md`.

### Green wave

**Wave:** 1 of 3
**Node:** n1
**Concurrent with:** none — this node is alone in its wave
**Blocks:** n2 (docks drones on parsed nests — needs `from_json` to accept nests and `Nests` to be
spawned), n3 (the fleet controller reads nests and drone ids via `nests_of`)

Real dependency edges, as opposed to the branch line:

    n1 → n2, n3      n2 → n5      n3 → n4      n4 → n5 (compile only: n5 adds an rpc to n4's service)

### Greenable independently?

**yes** — it owns everything its tests drive.

### Trunk-merge safety

**When this PR merges alone:** additive. A manifest without `drone_nest` parses and renders exactly
as today; `ELEMENT_KINDS` grows, no existing kind changes; proto field 8 is new, generated code is
checked in. `uv run pytest -q`, `cargo test --locked`, `trunk build` and the agent server keep
working. **Local dev data:** no change — the SQLite scenario store is schema-free JSON; existing
scenario versions stay valid. **Production data:** none.

## Background

The developer (2026-11-04): "the simulation should include drone nests, scattered on different
locations in scene. The agent would decide on what positions. The agent should also be able to
activate a drone, plan its trip route (on auto-pilot), adjust the route mid-course, do detours
etc. There can be multiple drones in-flight, but only input of 1 drone would be visible on screen
(the agent would decide which one) and that drone's RTAB-map and segmentation would be in process."

Decisions the same day: a **simulation-only scope exception** (no write path to PX4 or any real
flight controller; the survey pipeline stays passive); one RTAB-Map session and segmentation run
per drone; delivered as the five-node `#drone-fleet` stack based on `main` (after `#sim-traffic`
merged). This node is the nests and the written scope decision.

## Technical Changes

### State A (Current)

- `Element` (Rust, `scene_manifest.rs:57-64`) is internally tagged: `box`, `collapsed_building`,
  `building`, `person`, `vegetation`, `vehicle`. `from_json` enforces version 1 and one id
  namespace, then calls the per-area validators (`validate_weather_fire_vegetation`,
  `validate_buildings`, `validate_behaviours`, `validate_vehicles`).
- `scene_manifest/water.rs` lists `water: true` box surfaces (`Surface::of`).
- `world.rs` `Builder::element` dispatches each kind (`:281-289`).
- The Python mirror is `scenario_manifest.py`: `ELEMENT_KINDS`, `validate_manifest`, `element_ids`
  and `load_presets`, with kind modules beside it (`vehicles.py`, `water.py` — `_Surface` is
  private).
- The agent adds elements through `SimulationTools.AddElement`, a oneof whose fields 2–7 are used
  (`simulation_tools.proto:338-345`), via `simulation_handlers._element`.
- Golden scenarios in `tests/fixtures/sim_scenario/` are validated by both languages.
- No nest, dock or second drone exists anywhere.
- Scope text forbids flight control, navigation, path planning, tasking and route replanning
  (`docs/architecture.md:14-35`). It also says "No other component may have a simulation-only code
  path" (§4.3, line ~262). `AGENTS.md` and `README.md:17-20` repeat both points.

### State B (Target)

#### The element

```json
{"kind": "drone_nest", "id": "nest-roof", "position_enu": [12.0, 40.0, 9.0], "yaw_deg": 90.0, "drones": 2}
```

| Field | Rule |
|---|---|
| `id` | ASCII letters, digits, `-` (used in drone ids and URLs) |
| `position_enu` | the pad's centre at deck level, ENU m; `|east|, |north| ≤ 500`, `0 ≤ up ≤ 60` |
| `yaw_deg` | optional, default 0 — the pad's heading (drones face it when docked) |
| `drones` | optional, default 1, `1 ≤ drones ≤ 4`; drone ids `<id>-d1 … <id>-dN` |

The checks are `validate_nests()` in Rust and `fleet_nests.validate_nests()` in Python, with the
same messages, each naming the nest. Positions are in m.

- **Footprint.** The pad is a 2.4 m square, yawed. It may not intersect the footprint of a
  `building`, `collapsed_building` or a `box` with a collider. The exception is a pad whose `up` is
  at or above that element's top (±0.05 m), which is a rooftop nest.
- **Water.** The pad may not intersect a `water: true` surface.
- **Spacing.** Nest centres are ≥ 6 m apart. A scene holds at most 8 nests.
- **Ids.** Drone ids are added to the manifest id namespace, so `nest-a-d1` colliding with any id
  is `DuplicateId`.

#### Renderer

- `Builder::nest` spawns a pad at `position_enu`, turned by `yaw_deg`: a 2.4 m deck, a 0.1 m dark
  rim and an "H" marking from the existing material set. It has no collider beyond a thin deck
  cuboid, so the later drones can land on it.
- It tags the pad `NestPad { id }` and fills the `Nests` resource in manifest order; n2 docks
  drones from `Nests`.

#### Station and agent

- `fleet_nests.nests_of(manifest) -> tuple[Nest, ...]` (`Nest(id, pad_enu, yaw_deg, drone_ids)`)
  is the read API n3 builds on.
- `AddElement` with `drone_nest` (`DroneNestElement { id, position: EnuPoint, optional yaw_deg,
  optional drones }`).
- The `building-a-simulation-scene` skill gains a step: when the brief asks for drones, place 2–4
  nests far apart on open ground or flat roofs, then `get_scenario` to check.
- Preset `earthquake-fleet` = `earthquake-block` + `nest-sw` (open ground, 2 drones), `nest-ne`
  (open ground, 2 drones), `nest-roof` (a standing building's roof, 1 drone).

#### Scope amendment (text to write at Green; Wrap folds nothing further)

- **`docs/architecture.md` §1.** Add an IN-SCOPE row: "simulation only: the agent tasks the
  simulation's own drones (machine 3)". Keep flight control of any real aircraft, PX4/MAVLink
  commands and any flight-controller interface OUT OF SCOPE. Replace "SurMap has no write path to
  any flight controller" with that sentence plus: "the simulation's fleet commands exist only
  between the station and the Bevy simulation and have no path to PX4 or any flight controller".
- **§2.3.** The agent may launch, route, re-route and recall simulated drones from nests. The
  survey pipeline consumes the active drone's feed as it would a recorded session.
- **§4.3.** Narrow "No other component may have a simulation-only code path" to "No survey,
  perception or mapping component may…". Fleet tasking is simulation-only by design and is the
  one named exception.
- **`AGENTS.md` scope guardrail and `README.md`.** The same exception, in one sentence each.

### Delta (What's Changing)

#### examples/bevy-sitl-poc

- `scene_manifest.rs` (+`DroneNest`, variant, arms, `mod fleet`), `scene_manifest/fleet.rs` (new),
  `scene_manifest/tests/fleet.rs` (new), `world.rs` (`Builder::nest`, `Nests`, `NestPad`),
  `flight.rs:3` doc comment.

#### surmap

- `simulation/fleet_nests.py` (new), `simulation/water.py` (`water_surfaces`),
  `simulation/scenario_manifest.py` (kind, ids, preset), `agent/tools/simulation_handlers.py`,
  `proto/surmap/agent/v1/simulation_tools.proto` + generated code,
  `agent/skills/building-a-simulation-scene/SKILL.md`.
- Tests: `tests/test_sim_fleet_nests.py` (new), `tests/test_agent_simulation_tools.py` (nest arm),
  `tests/fixtures/sim_scenario/fleet-nests.json` (new).

#### docs

- `docs/architecture.md`, `AGENTS.md`, `README.md` (scope).

## Verification

**Method:** V1 fail→pass — acceptance tests over the agent's `add_element` and the preset, plus
Rust/Python rule tests over the shared golden.
**Command:** `uv run pytest -q tests/test_sim_fleet_nests.py tests/test_agent_simulation_tools.py`
and `cd examples/bevy-sitl-poc && cargo test --locked fleet`
**Before:** the new tests fail — `drone_nest` is an unknown element kind (Python `ScenarioInvalid`,
Rust serde unknown variant) and the stubs raise.
**After:** all pass. Also, `cargo test` parses `fleet-nests.json` and the `earthquake-fleet`
preset output.

Supporting evidence (not a rung): native still `--screenshot <dir> --at 5 --scenario
earthquake-fleet` (`overview.png`) shows three pads, one on a roof. It is reviewed at wrap.

## Acceptance Tests

- `the_agent_places_a_nest_and_the_scenario_keeps_it` — `add_element` with `drone_nest` → stored
  manifest has the nest; `nests_of` names `nest-a-d1`, `nest-a-d2`.
- `a_nest_inside_a_building_is_refused_with_the_rule`, `…_on_water_…`, `…_outside_the_bounds_…`,
  `…_too_close_to_another_nest_…`, `…_with_five_drones_…`, `…_whose_drone_id_is_taken_…`.
- `a_nest_on_a_roof_is_accepted`.
- `the_earthquake_fleet_preset_has_three_nests_and_five_drones`.
- Rust: `a_station_written_fleet_scenario_is_a_valid_manifest` (golden),
  `every_element_kind_is_declared_in_json` extended, rule tests mirroring the Python ones.

## Prerequisites

Deferred-work scan (`src/surmap/docs/todo/`, `src/surmap/docs/code-issues/`,
`docs/surmap/deferred-answers/`):

| Item | Verdict |
|---|---|
| `todo/2026-11-03-bevy-visual-checkpoints-v3-v5.md` | — unrelated (browser stills parity) |
| `code-issues/private-reach-agent-tools-workspace.md` | — unrelated (demo runs) |
| everything else | — unrelated |

`examples/bevy-sitl-poc` has no `docs/code-issues/` directory — never analyzed, not known clean.
Nothing blocks.

## Decisions & Trade-offs

- **A manifest element, not a separate fleet document.** Nests are scene geometry (they are drawn,
  they collide, and the agent places them like buildings). Versioning, validation and the golden
  fixtures come with the element for free. What flies is not scene data, and it lives in n2/n3.
- **Drone ids are derived (`<nest>-dK`), not declared.** One field per nest is all the agent writes.
  The ids are stable for the autopilot log (n2) and the tools (n4).
- **Rooftop nests are allowed.** Real docks are often on roofs, and a roof start gives the
  autopilot a non-trivial climb. A pad overlapping a building below its top is refused, so a nest
  never sits inside a wall.
- **Geometry rules are footprint-only (2D AABB/yawed box), not mesh collision.** They match how
  `water.rs` and `vehicles` already validate, and stay identical in both languages.
- **`[G]` on Sonnet only** (developer, 2026-11-04, whole stack). The rubric would size this node's
  Green at Haiku · xhigh (complexity 4); Sonnet · high instead. It trades token cost for fewer
  out-of-depth retries on a two-language, proto-touching node.
- **The scope amendment rides with n1**, not as a docs-only node. It must land before any code that
  flies a drone, and n1 is the bottom of the stack. A docs-only node would need a verification
  method that proves nothing.
