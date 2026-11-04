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
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · every red test passes (Rust 195/195 before the detector work; Python incl. the new detector tests); the bus is pinned as one named CC BY 3.0 exception (developer decision, 2026-11-04; see *Decisions*); detector cross-check: car, bus and truck clear the 20 % bar, the train does not (0/6, TODO `src/surmap/docs/todo/2026-11-04-train-detectors-blind.md`)
  - [x] Pin glTF packs in `examples/bevy-sitl-poc/assets/assets.lock.json` (criteria in *Assets*), `uv run python scripts/fetch_sim_assets.py` verifies them — car, truck, locomotive and carriage pinned (Quaternius, CC0-1.0, via poly.pizza); the bus pinned as CC BY 3.0 with its attribution (Poly by Google, poly.pizza/m/4CPpvEmrMoF); 102/102 verified
  - [x] Rust `scene_manifest.rs`: `vehicle` element, validated (known class, `cars` only on `train`, tree validated as `Target::Object`)
  - [x] Rust `vehicle.rs` (pure): `VehicleDef` loader, `Drive` kinematics, carriage placement along the travelled path, wheel angle
  - [x] Rust runtime: spawn the class glTF (or `glb` override) under a moving root, tick with the people at 10 Hz, spin wheel nodes, carriages trail — compiles for native and `wasm32`; not yet seen on screen (the native still is a Wrap check)
  - [x] Tracks: `kind` and `yaw_deg` on every `object_tracks.jsonl` object; vehicles added; `bevy_capture` reads `object_kinds`/`object_yaw_deg`
  - [x] Python `scenario_manifest`: `vehicle` in `ELEMENT_KINDS` with the same rules; preset `street-traffic`; golden `tests/fixtures/sim_scenario/street-traffic.json` parsed by Rust
  - [x] Proto `VehicleElement` in `AddElementRequest`; regenerated code; handler (no test-checked docs table — `docs/agent.md` is prose, its vehicle line is Wrap's)
  - [x] Gates green: `ruff format`, `ruff check --no-cache`, `mypy`, `pytest -q`, `cargo test --locked`, `cargo check --target wasm32-unknown-unknown` (the wasm warning is pre-existing, `calibration.rs`)
  - [x] Detector label map (red first): `detection_eval.COCO_LABELS` gains `bus`, `truck`, `train`; tracked vehicles are projected at their per-frame position and heading; "found as another vehicle" is counted per kind; the score script's columns follow the kinds present
  - [x] Record `street-traffic` natively (`--colour --jpeg --rate-hz 1`) into the scratchpad (frames are not committed) and score it with `scripts/score_sim_detections.py` at 0.3 — *before* numbers (128 frames, one lap)
  - [x] Bar: for car, bus, truck and train the best profile finds it in at least 20 % of its object-frames in view, and no class is 0 across all profiles; where it misses, improve realism and re-measure (at most 3 iterations per class) — bus 5/16, truck 10/14, car 34/90 clear it; the train is 0/6 after three iterations
  - [x] Record the before/after table in `docs/simulation/bevy-simulation.md` § *On-board detectors (measured)* and in *Verification* (V3); a class still under the bar gets a TODO under `src/surmap/docs/todo/`

**Resolved at wf 3 (*Assets*: the bus).** The halt asked for a decision: (a) a named CC BY 3.0 bus,
(b) a CC0 bus elsewhere, or (c) dropping the bus from `street-traffic`. The developer chose (a) on
2026-11-04. The bus is Poly Pizza's *Bus* by Poly by Google (`4CPpvEmrMoF`), the closest to a coach
of the six CC BY 3.0 buses measured (see *Decisions*).
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

`glb`, `model_scale` (uniform scale of the class glTF and its carriages, default 1 — added at wf 3
for the bus, whose pack is authored off metres), `length_m`/`width_m`/`height_m` (collider and truth extent), `wheel_nodes` (glTF node-name
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
`behaviour_tree`); preset `street-traffic` = the disaster block with two cars on the avenue, a
yellow bus and a truck on the cross street, a parked car, and a rail line (`box`, material `ballast`) along
the block's west edge with a 6-carriage train.

### Assets

Pinned in `assets.lock.json` (`member` from a zip where needed), licence **CC0-1.0** by default,
source page recorded. The one exception, by the developer's decision of 2026-11-04: a named CC BY
3.0 bus, whose pin carries an `attribution` (author and model page); a non-CC0 pin without one is
refused by the loader, and a test names the bus as the only one. Criteria: glTF/GLB, separable
wheel nodes for road classes (an empty `wheel_nodes` list when the model has none), and real-world
scale, or a documented `model_scale` in the class file. Kenney's *Car Kit* and *Train Kit* could
not be pinned (signed, expiring download links); the Quaternius CC0 packs cover car, truck,
locomotive and carriage.

## Verification

- **V1** — Rust (`cargo test --locked`): `Drive` never exceeds speed/accel/turn limits and reaches
  a path end; determinism (same scenario, same track); carriages on the path at spacing through a
  90° bend; wheel angle from distance; manifest rules (unknown class, `cars` on a non-train, bad
  `glb`, tree target) and the golden `street-traffic.json`; track line with `kind`/`yaw_deg`.
  Python (`uv run pytest -q`): `vehicle` validation mirrors Rust; preset; `add_element` vehicle via
  the tool; `load_bevy_capture` reads kinds and yaw; an acceptance test over a recorded
  `street-traffic` capture fixture (tracks present, none in `ground_truth.json`).
- **V3 — detector cross-check (a deterministic recorded command).** From `examples/bevy-sitl-poc`,
  with `tests/fixtures/sim_scenario/street-traffic.json` copied to `assets/scenarios/` and
  `uv run python scripts/fetch_coral_model.py` run: `BEVY_ASSET_ROOT=$PWD cargo run -- --record <dir>
  --scenario street-traffic --colour --jpeg --rate-hz 1 --start 0 --frames 128`, then
  `uv run python scripts/score_sim_detections.py <dir>`. Bar: for car, bus, truck and train the best
  of the three profiles finds it in ≥ 20 % of its object-frames in view, and no class is 0 on all.
  Recorded, 2026-11-04 (object-frames found / in view, score 0.3; before → after):

  | Profile | Car | Bus | Truck | Train | FP |
  |---|---|---|---|---|---|
  | efficientdet-lite0 | 12/90 → 12/90 | 1/16 → **5/16** | 1/13 → **8/14** | 0/6 → 0/6 | 84 → 85 |
  | ssd-mobilenet-v2 | 3/90 → 2/90 | 0/16 → 0/16 | 0/13 → 1/14 | 0/6 → 0/6 | 35 → 32 |
  | ssdlite-mobiledet | 33/90 → **34/90** | 0/16 → 1/16 | 2/13 → **10/14** | 0/6 → 0/6 | 355 → 344 |

  Result: car 38 %, bus 31 %, truck 71 % clear the bar; the train does not (0/6 on all profiles after
  three iterations) — TODO `src/surmap/docs/todo/2026-11-04-train-detectors-blind.md`. Same table in
  `docs/simulation/bevy-simulation.md` § *Road and rail vehicles*. Unit tests:
  `tests/test_sim_detection_eval.py` (label map, tracked-vehicle footprints, confusions).
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
- **Developer decision, 2026-11-04 (answer to the wf 3 halt, option a):** the CC0-only rule is relaxed
  for one named bus — *"Bus" by Poly by Google* (https://poly.pizza/m/4CPpvEmrMoF), CC BY 3.0 —
  credited in the lock's `attribution` and in `docs/simulation/bevy-simulation.md`. No other
  non-CC0 asset is allowed; `test_the_only_pin_off_cc0_is_the_named_cc_by_bus` holds that line.

**Green decisions made without review (wf 3):**
- The approach speed is capped at `BEARING_SHARE` (½) of turn rate × distance, where the bearing is misaligned, and at a creep cap on stopping goals. The first draft overshot a stopping goal by about 1 m (braking-distance caps lag at low speed), so a stopping goal now creeps. A drive-through point counts as reached when the drive passes it: the runner is placed on the point, so the tree advances (a slow turner cannot hit a path corner).
- `model_yaw_deg` (not in State B): the turn that points a glTF's nose along the vehicle's forward. The Quaternius car and truck face +Z (180°); the locomotive faces −X (−90°). `wheel_nodes` are used for road classes only (no spin for the rail wheels). The wheel pivot is the wheel mesh's own bounds centre, so a wheel rolls in place.
- Models are Quaternius CC0 (poly.pizza), not Kenney: Kenney's links are signed and expire. Car, truck and locomotive units are real metres or a 100× node scale that glTF applies. The fetch opener sends a `Referer` for `static.poly.pizza`, which refuses hot links otherwise (`REFERERS`, one host).
- `resolve_target` accepts a `vehicle` (the e2e test reads its drive with `behaviour_of`); a vehicle's tree is validated as an object's.
- Trains are not in a rail graph; carriages are separate roots placed on the locomotive's travelled path.
- The bus, chosen among the bus-titled CC BY 3.0 models on Poly Pizza: six were measured from their
  glTF (authored size, origin, poster); the seventh (`2_1dZHNPJqJ`, 25,046 triangles) was not
  downloaded. Length/width ratios were 1.0–2.6 for five of them (a bus is about 4.7), and one sits
  1.7 km or more from its origin. The Google *Bus* (`4CPpvEmrMoF`, 2,226 triangles, one coach mesh,
  length/width 3.1) is the closest to a coach.
- The bus's scale: the model is authored at 157.5 × 50.1 × 48.8 units, not metres. The new class
  field `model_scale` 0.07 gives 11.0 × 3.5 × 3.4 m. The length keeps the planned 11 m; the width
  and height are the model's own proportions at that length (wider than a real 2.5 m bus).
  `model_scale` is a new class-file field (default 1, must be > 0), applied to the class glTF and
  its carriages; this extends the class format and is recorded here for review.
- The bus's forward: `model_yaw_deg` 180 (nose at +Z). The poster's camera (θ 0.87 rad) shows the
  windscreen end on the left, which is +Z in that view; the +Z end is also the wider one (mirror
  arms: half-width 25.0 against 22.6 at the other end). Verify on the native still at wrap.
- The bus has no separable wheel meshes (one coach mesh), so `wheel_nodes` is `[]`: its wheels do
  not spin. The developer's answer allows an empty list; a separable pack would be another pin.
- Checks: `scripts/fetch_sim_assets.py` verifies 102 pins (the bus's sha256 `594f1e51…`); the GLB is
  a valid glTF 2.0 file; my GLB inspector agrees with the fetched Quaternius car (1.81 × 1.18 ×
  4.22 m against its class 1.8 × 1.2 × 4.2) and truck. The bus is not yet seen on screen (Wrap).
- **Detector cross-check, decided without review (wf 3, 2026-11-04):** (1) `bus`, `truck`, `train`
  answer only to their own COCO label; `car` keeps {car, truck, bus}, so main's car/person numbers
  do not move. (2) A tracked vehicle the ground truth does not list gets its class footprint
  (copied into `detection_eval.VEHICLE_FOOTPRINT_M`, since the renderer's class files are not a
  Python dependency) and the axis-aligned box of its yawed rectangle, so a diagonal vehicle's
  expected box is slightly larger than the vehicle. A train is its locomotive; carriages are not
  tracked. (3) "Found as another vehicle" counts a missed vehicle covered by a car/bus/truck/train
  detection and removes that detection from the false positives. (4) Realism levers kept: bus tint
  school-bus yellow (red scored 0/16, white 1/16); truck moved to the cross street and class scaled
  1.25 (`truck.vehicle.json`: 6.6 × 3.4 × 3.6 m, wheel radius 0.55); `street-traffic` golden
  regenerated. Reverted: train rail and speed changes (no gain). (5) Recording the bar needs one lap
  (128 frames) so the train, in view for six frames, is in it. (6) A capture's lighting varied run to
  run once (25 % darker); that run was discarded and re-recorded. The pinned assets were fetched
  (`fetch_sim_assets.py`) and `assets/scenarios/street-traffic.json` copied in locally, neither is
  committed.
