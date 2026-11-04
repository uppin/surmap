# Changeset: road and rail vehicles that drive

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — a new element kind end to end (Rust manifest, pure vehicle kinematics over the
existing behaviour-tree runtime, glTF spawning with wheel nodes and carriages, recorder tracks),
Python validation/proto/tool/preset, pinned CC0 glTF packs; one native visual checkpoint

PRD: `PRD-2026-11-04-sim-road-rail-vehicles.md` · Discovery:
`2026-11-04-sim-road-rail-vehicles-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-pr-stack` Plan — PRD, changeset, initial discovery · these files @ `063079f` (`/plan-pr-stack` pass 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-11-04 `/plan-pr-stack` Red — acceptance and failing lower-tier tests, committed · Rust 26 red / 167 green; Python 16 red (2 acceptance, 14 unit/it) — commit 2
  - [x] Build and baseline healthy — `cargo test --locked` 167/167, `cargo check --target wasm32-unknown-unknown` ok, `uv run mypy` clean (486 files); `uv run pytest -q` 1891 passed, 1 pre-existing local failure (`tests/test_survey_cm5_rtabmap_e2e.py::test_euroc_pairs_stream_real_rtabmap_poses_and_points`, needs a local RTAB-Map sidecar — not this stack's)
  - [x] Stubs this node owns (`vehicle.rs`, `behaviour::Goal` + `Runner::goal`, `Element::Vehicle`, `validate_vehicles`, `Body.kind`/`yaw_deg`, `surmap.simulation.vehicles`, `BevyCapture.object_kinds`/`object_yaw_deg`, proto `VehicleElement`)
  - [x] Acceptance tests written and failing for the right reason (`tests/test_sim_vehicle_e2e.py`)
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ⛔ `/green` Green — implement until every red test passes · every red test passes (Rust `cargo test --locked` 193/193; Python vehicle, tool and capture tests 32/32; `pytest -q` 2049 passed, 36 skipped); halted on the *Assets* criterion: no pinnable CC0 bus (see *Halt at wf 3* below)
  - [ ] Pin CC0 glTF packs in `assets/assets.lock.json` (criteria in *Assets*), `uv run python scripts/fetch_sim_assets.py` verifies them — ⛔ car, truck, locomotive and carriage pinned (Quaternius, CC0-1.0, via poly.pizza; 101/101 verified); **bus not pinned**
  - [x] Rust `scene_manifest.rs`: `vehicle` element, validated (known class, `cars` only on `train`, tree validated as `Target::Object`)
  - [x] Rust `vehicle.rs` (pure): `VehicleDef` loader, `Drive` kinematics, carriage placement along the travelled path, wheel angle
  - [x] Rust runtime: spawn the class glTF (or `glb` override) under a moving root, tick with the people at 10 Hz, spin wheel nodes, carriages trail — compiles for native and `wasm32`; not yet seen on screen (the native still is a Wrap check)
  - [x] Tracks: `kind` and `yaw_deg` on every `object_tracks.jsonl` object; vehicles added; `bevy_capture` reads `object_kinds`/`object_yaw_deg`
  - [x] Python `scenario_manifest`: `vehicle` in `ELEMENT_KINDS` with the same rules; preset `street-traffic`; golden `tests/fixtures/sim_scenario/street-traffic.json` parsed by Rust
  - [x] Proto `VehicleElement` in `AddElementRequest`; regenerated code; handler (no test-checked docs table — `docs/agent.md` is prose, its vehicle line is Wrap's)
  - [x] Gates green: `ruff format`, `ruff check --no-cache`, `mypy`, `pytest -q`, `cargo test --locked`, `cargo check --target wasm32-unknown-unknown` (the wasm warning is pre-existing, `calibration.rs`)

**Halt at wf 3 (*Assets*: no pinnable CC0 bus).** Candidates checked, none accepted:
- Kenney *Car Kit* / *Train Kit* (CC0): kenney.nl serves the zip only through a signed, expiring link (`/download-link/<id>` → `?expires=`); the bare URL returns 404, so it cannot be pinned.
- Poly Pizza searches `bus`, `coach`, `minibus`, `city bus`, `double-decker`, `school bus`, `transit` (24 results each; the `page` parameter returns the same page): every bus is CC-BY 3.0. Non-bus CC0 hits (`Locomotive Passenger Carriage`, `Taxi`) do not fit the class.
- Decision for the developer: (a) accept a named CC-BY 3.0 bus, with attribution in the lock's `source`; (b) find a CC0 bus elsewhere; or (c) drop the bus from `street-traffic`, which changes the golden test, so it needs consent.
- Hazard, unresolved: `assets/vehicle/bus.vehicle.json` names `models/quaternius/bus.glb`, which is not pinned. The scene waits on every glTF it spawns (`scene_ready`), so a scenario with a bus will not start recording until a bus is pinned. The class file parses, so the Rust test passes.
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (tests + native still of `street-traffic` reviewed)
  - [ ] `docs/simulation/bevy-simulation.md` — *Vehicles* section; `docs/agent.md` — `add_element` vehicle
  - [ ] `docs/simulation/changelog/2026-11-04-sim-road-rail-vehicles.md`
  - [ ] Lint (`ruff --no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Stack Context

Stack `sim-traffic` (slug `sim-traffic`) — **1 of 3** · PR [#106](https://github.com/uppin/surmap/pull/106).
**Kind:** Feature · adds — **Workflow:** feature preset; pass-2 route `/plan-red` Steps 7–9.
Branch `pr-1-sim-traffic`, base `main`; successor `pr-2-sim-traffic`.
Seam: a new element kind and its own module (`vehicle.rs`); shares only the behaviour runtime and
the recorder's track line with people.
**Owned API:** `Element::Vehicle` / `Vehicle` (manifest), `vehicle.rs` (`VehicleClass`,
`VehicleDef`, `Drive`, `carriage_poses`, `wheel_angle`), `assets/vehicle/<class>.vehicle.json`,
the track line's `kind` and `yaw_deg` fields (`actors::Body`), Python `vehicle` validation and
`street-traffic` preset, proto `VehicleElement`, `BevyCapture.object_kinds` / `.object_yaw_deg`.

### Green wave

**Wave:** 1 of 2 · **Node:** n1 · **Concurrent with:** n2 · **Blocks:** n3 (the vehicle element,
`Drive` kinematics and spawning it adds water classes to).
Edges: `n1 → n3`; n2 is independent.
**Greenable independently?** yes.

### Trunk-merge safety

Additive: manifest version stays 1 and every new field is optional, so existing scenarios and the
station's stored scenarios render unchanged; no SQLite schema change (scenarios are JSON). The
track line gains fields — `load_bevy_capture` ignores unknown keys today, and the committed capture
fixtures stay valid. New assets are fetched (git-ignored); a checkout without them still builds and
tests (manifest tests do not load GLBs). No production data touched.

## Background

The developer (2026-11-04): "for the WASM simulation, let's add realism to people and make ability
for cars, busses, trucks, trains etc. to drive. We should support ships, boats too." Decisions the
same day: CC0 rigged glTF first (pinned, animation clips played); a 3-PR stack — this node road and
rail vehicles, n2 people, n3 boats and ships.

## State A (before)

Vehicles exist only as static `models` (Poly Haven `covered_car`, collider box, ground-truth kind
`car`). People move by behaviour trees at 10 Hz (`actors.rs`, `behaviour/tick.rs`) at exactly
their node's `speed_m_s` — no acceleration or turn limits. `object_tracks.jsonl` objects carry
`id`, `enu`, `action`.

## State B (after)

### In the manifest

```json
{"kind": "vehicle", "id": "bus-1", "class": "bus", "position_enu": [-2.5, -40.0, 0.0], "yaw_deg": 90.0,
 "behaviour": {"node": "repeat", "child": {"node": "sequence", "children": [
   {"node": "follow_path", "enu": [[-2.5, 120.0]], "speed_m_s": 8.0},
   {"node": "idle", "s": 10.0},
   {"node": "follow_path", "enu": [[-2.5, -40.0]], "speed_m_s": 8.0}]}}}
{"kind": "vehicle", "id": "freight", "class": "train", "cars": 6,
 "position_enu": [-60.0, -80.0, 0.0], "behaviour": {"node": "follow_path", "enu": [[-60, 200]], "speed_m_s": 15.0}}
```

| Field | Meaning |
|---|---|
| `class` | `car` \| `bus` \| `truck` \| `train` (n3 adds `boat`, `ship`) — picks `vehicle/<class>.vehicle.json` |
| `position_enu`, `yaw_deg` | start pose (yaw counter-clockwise from east, as `models`) |
| `behaviour` | optional tree, validated as `Target::Object` (no `set_wind`); parked when absent |
| `glb` | optional override of the class glTF (relative asset path, `.glb`/`.gltf`) |
| `cars` | trains only, ≥ 0 carriages behind the locomotive (default 0) |
| `tint` | optional sRGB multiplier on the glTF's base colours |
| `ground_truth` | default `true`: tracked in `object_tracks.jsonl` with `kind` = `class` |

### Class files (`assets/vehicle/<class>.vehicle.json`, data, no rebuild)

`glb`, `length_m`/`width_m`/`height_m` (collider and truth extent), `wheel_nodes` (glTF node-name
prefixes spun about their axle), `wheel_radius_m`, `max_speed_m_s`, `accel_m_s2`, `brake_m_s2`,
`turn_rate_deg_s`, and for `train`: `carriage_glb`, `carriage_spacing_m`. Shipped values (planned):
car 15 m/s · 3 m/s² · 6 m/s² · 45°/s; bus 12 · 1.2 · 3 · 20; truck 12 · 1.0 · 3 · 18; train
30 · 0.5 · 1.0 · 6.

### Kinematics (`vehicle.rs`, pure, deterministic)

The tree's runner proposes where the body should go this tick (`Runner.position`); `Drive` turns
that into a vehicle's motion: speed eases toward the node's `speed_m_s` (capped at
`max_speed_m_s`) at `accel_m_s2`, slowing at `brake_m_s2` to stop at a `move_to`/path end; heading
turns toward the target at most `turn_rate_deg_s`; the body moves along its heading. The runner's
own position is reset to the vehicle's, so trees (`near_object`, path ends) see where the vehicle
really is. A train's heading follows its path; carriages are placed at `k × carriage_spacing_m`
behind the locomotive **along the travelled polyline** (`carriage_poses`), so they stay on the
track through bends. Wheels turn by distance / `wheel_radius_m`.

### Ground truth

`object_tracks.jsonl` objects gain `kind` (`person`, `car`, …) and `yaw_deg` (ENU, counter-clockwise
from east); a train's carriages are objects `<id>/car-<k>`. `ground_truth.json` never lists a
moving vehicle; a vehicle with no tree is parked and still only a track (it may be given one
later). `load_bevy_capture(...).object_kinds: dict[str, str]`, `.object_yaw_deg:
dict[int, dict[str, float]]`.

### Station and agent

`scenario_manifest.py`: `vehicle` kind with the renderer's rules; `add_element` takes
`VehicleElement {id, class, position, yaw_deg, cars, behaviour_json}` (the tree is validated by
`behaviour_tree`); preset `street-traffic` = the disaster block with two cars and a truck on the
avenue, a bus on the cross street, a parked car, and a rail line (`box`, material `ballast`) along
the block's west edge with a 6-carriage train.

### Assets

Pinned in `assets.lock.json` (`member` from a zip where needed), licence **CC0-1.0** only, source
page recorded. Criteria: glTF/GLB, separable wheel nodes for road classes, real-world scale or a
documented scale in the class file. Candidates: Kenney *Car Kit* (sedan, taxi, police, van, truck,
ambulance, firetruck, garbage truck) and *Train Kit* (locomotive, wagons) — kenney.nl, CC0; a bus
from Quaternius (Poly Pizza, CC0) if the Car Kit lacks one. If no pinnable CC0 file meets the
criteria for a class, the Green row halts ⛔ with the candidates found — no non-CC0 substitute.

## Verification

- **V1** — Rust (`cargo test --locked`): `Drive` never exceeds speed/accel/turn limits and reaches
  a path end; determinism (same scenario, same track); carriages on the path at spacing through a
  90° bend; wheel angle from distance; manifest rules (unknown class, `cars` on a non-train, bad
  `glb`, tree target) and the golden `street-traffic.json`; track line with `kind`/`yaw_deg`.
  Python (`uv run pytest -q`): `vehicle` validation mirrors Rust; preset; `add_element` vehicle via
  the tool; `load_bevy_capture` reads kinds and yaw; an acceptance test over a recorded
  `street-traffic` capture fixture (tracks present, none in `ground_truth.json`).
- **Supporting evidence (not a rung)** — native still `--screenshot <dir> --at 20 --scenario
  street-traffic`, reviewed at wrap: vehicles on the roads, train on its track, wheels not floating.

## Red tests (commit 2)

| Test | Validates |
|---|---|
| `tests/test_sim_vehicle_e2e.py::test_an_agent_turn_adds_a_truck_that_drives_up_the_avenue` | agent `add_element` vehicle → served, valid, with its tree |
| `tests/test_sim_vehicle_e2e.py::test_the_served_street_traffic_preset_is_the_golden_the_renderer_validates` | preset served = golden `tests/fixtures/sim_scenario/street-traffic.json` (written at Green from the preset) |
| `tests/test_sim_vehicle_manifest.py` (11) | valid bus/train; refusals naming id + reason (class, cars, glb, set_wind, tint); preset classes; preset = golden |
| `tests/test_agent_simulation_tools.py` — vehicle added; unknown class `INVALID_ARGUMENT` | handler |
| `tests/test_bevy_capture.py::test_a_capture_carries_what_each_tracked_body_is_and_its_heading_per_frame` | `object_kinds`, `object_yaw_deg` |
| `src/vehicle/tests.rs` (19) | class file name/kind, `VehicleDef` rules, shipped class files, accel/max-speed/turn limits, stop without overshoot, brake without goal, no circling, wheel angle, tree to path end, determinism, parked, carriages on track through a bend |
| `src/scene_manifest/tests.rs` (7) | train with cars; `cars` refused off trains; `glb` override rules and asset path; no `set_wind`; golden parses with all four classes |
| `src/actors/tests.rs` (2) | track line carries `kind`/`yaw_deg` (the existing exact-JSON test now pins the extended contract); a walking figure tracked as `person` facing its way |

## Prerequisites

Deferred-work scan (`src/surmap/docs/todo/`, `src/surmap/docs/code-issues/`):
`2026-11-03-bevy-visual-checkpoints-v3-v5.md` — ℹ unrelated (browser checkpoint); the other
`2026-11-03-bevy-*` records — ℹ unrelated. Nothing blocks.

## Decisions & Trade-offs

- Vehicles reuse the behaviour-tree runtime rather than a route format of their own: one
  mechanism, already validated by station and renderer, already editable by the agent's tools.
- `Drive` limits motion after the tree proposes it, instead of adding vehicle nodes: trees stay
  target-agnostic; a vehicle is just a body that cannot turn on the spot.
- Kenney/Quaternius CC0 packs are stylised low-poly — the pinned-CC0 rule wins over photo-realism;
  a scenario may override any vehicle's `glb` with a station-library asset (e.g. Sketchfab CC BY).
- `Drive` reads the running leaf's **goal** (`behaviour::Goal`: point, speed, `stop` at a path's
  end) rather than the runner's stepped position, so it can brake in time; `VehicleBody` resets the
  runner to the vehicle's real place each tick. Speed is held so the turn radius never circles the
  goal.
- The proto field is `vehicle_class` (`class` is a Python keyword); the manifest key stays `class`.
- The existing exact-JSON track-line test was updated to the extended contract in commit 2, so it is
  red until Green emits `kind` and `yaw_deg`.
- Trains follow their path, not a rail graph: no switching or collision; out of scope.

**Green decisions made without review (wf 3):**
- The approach speed is capped at `BEARING_SHARE` (½) of turn rate × distance, where the bearing is misaligned, and at a creep cap on stopping goals. The first draft overshot a stopping goal by about 1 m (braking-distance caps lag at low speed), so a stopping goal now creeps. A drive-through point counts as reached when the drive passes it: the runner is placed on the point, so the tree advances (a slow turner cannot hit a path corner).
- `model_yaw_deg` (not in State B): the turn that points a glTF's nose along the vehicle's forward. The Quaternius car and truck face +Z (180°); the locomotive faces −X (−90°). `wheel_nodes` are used for road classes only (no spin for the rail wheels). The wheel pivot is the wheel mesh's own bounds centre, so a wheel rolls in place.
- Models are Quaternius CC0 (poly.pizza), not Kenney: Kenney's links are signed and expire. Car, truck and locomotive units are real metres or a 100× node scale that glTF applies. The fetch opener sends a `Referer` for `static.poly.pizza`, which refuses hot links otherwise (`REFERERS`, one host).
- `resolve_target` accepts a `vehicle` (the e2e test reads its drive with `behaviour_of`); a vehicle's tree is validated as an object's.
- Trains are not in a rail graph; carriages are separate roots placed on the locomotive's travelled path.
