# Initial Discovery: The survey agent flies the simulation's fleet (#drone-fleet n4)

**Changeset**: [2026-11-04-fleet-tools.md](./2026-11-04-fleet-tools.md)
**Source**: Explorations 1–4 are the `#drone-fleet` stack's whole-work passes, copied verbatim at `/plan-pr-stack` 4b
**Date**: 2026-11-04
**Passes**: 4

## Combined Conclusions

**For this node:** Exploration 2 §4.1–4.3 (proto → codegen `PROTOS` → handler factory → `services.py` module → `app.build_agent_description` + `binding._HANDLER_SERVICES`; execution kinds; `EnuPoint`), §6 (test conventions: handler `call`, `ScriptedChatModel` e2e on `HypercornHost`), §4.8 (the passive statements in `docs/agent.md`, the SYSTEM_PROMPT, `using-the-map`). Follow-up below: `PROTOS` is `scripts/gen_agent_rpc.py:28`; `_HANDLER_SERVICES` is `agent/server/binding.py:37`; skills are `agent/skills/<name>/SKILL.md`, and `using-the-map/SKILL.md:9-12` declines vehicle commands.

**Packages in play**: `examples/bevy-sitl-poc` (Rust/Bevy, wasm + native), `src/surmap/simulation`
(manifest mirror, bridge, wire, capture), `src/surmap/agent` (tools, server, protos),
`src/surmap/slam` (streaming RTAB-Map), docs (`docs/architecture.md`, `AGENTS.md`, `README.md`,
`docs/agent.md`, `docs/simulation/bevy-simulation.md`).

**Current state (State A).**

- **Sim: one hard-coded drone.** `Drone` is a unit marker. Every system (`fly_scripted`,
  `follow_drone_rig`, `chase_camera`, `read_controls`, `update_status`) uses `single()`. `Flight`,
  `StereoFeeds`, `CameraProfile` and `Recorder` are global. The eyes are top-level cameras,
  re-posed from the body every frame. The flight is the pure `SurveyLoop::pose_at(t)`, and the
  recorder recomputes ground-truth pose from it.
- **No headless Bevy harness.** Every Rust test targets pure functions (`cargo test --locked` in
  `bevy-wasm-test.yml`; `ci.yml` has no cargo step). An autopilot must therefore be a pure
  function of (command log, t) to be testable, the same way `flight.rs` is.
- **No live channel into the sim.**
  - The sim reads the manifest once, `?scenario=` once, and the keyboard. It has no reload,
    socket or command path.
  - The Rust wire (`hello`/`pair`) is encode-only and never sent. The wasm WebSocket client is
    the open todo `2026-11-03-bevy-live-websocket-stream.md` (M6).
  - `Cargo.toml` and `index.html` promise "nothing is sent to a backend".
  - The agent server serves `/sim/` and manifests over GET only.
- **Manifest.**
  - Internally tagged `Element` kinds, validated identically in Rust (`scene_manifest.rs`, with
    submodule validators) and Python (`scenario_manifest.py` `ELEMENT_KINDS`, `validate_manifest`).
  - The agent adds elements through `SimulationTools.AddElement`, a proto oneof.
  - Shared golden fixtures live in `tests/fixtures/sim_scenario/`.
  - Version 1, with additive optional fields.
  - No geodetic origin in the sim; `disaster_world.enu_to_wgs84` exists in Python.
- **Agent tools.**
  - Flow: proto with `default_execution` → `scripts/gen_agent_rpc.py` → handler factory →
    `services.py` module → registration in `app.py` and `binding.py:_HANDLER_SERVICES` (rpc names
    are global).
  - Long operations are SYNC 30 DETACH. Jobs are per conversation and not persistent, so
    station-level state lives in stores (`ScenarioStore`, `MapSceneStore`).
  - Map routes are display-only lon/lat in `MapSceneStore`; the chat UI polls a revision every 2 s.
- **Perception.**
  - One WebSocket connection is one `BevyStreamSession`, which is one backend. The wire has no
    drone or session id.
  - `StreamingRtabmapBackend` keeps its map in memory, per sidecar process, and does its own
    visual odometry (sim pose is ground truth only).
  - On a gap, `Odom/ResetCountdown: 1` resets odometry and starts a new sub-map in the same graph.
  - `DemoRunHost` allows one engine. Bevy streams are not runs in `RunHistoryStore`.
  - SAM's per-frame seam is `_SamWorker.submit(frame_id, t_ns, jpeg)`.
- **Scope statements** that conflict with agent-tasked sim drones:
  - `docs/architecture.md` §1 (14–35), §2.3 (62–76), §4.3 (262: "No other component may have a
    simulation-only code path"), §10 and §11.
  - `AGENTS.md` scope guardrail; `README.md:17-20`.
  - `docs/agent.md` (112, 181–182, 290) and the SYSTEM_PROMPT in `agent/server/app.py:116-117`.
  - `bevy-simulation.md:212-213`; `flight.rs:3`.
  - Proto headers (`map_tools`, `survey_tools`, `simulation_tools`) and
    `.agents/skills/product-overview/SKILL.md:9,42`.

**Constraints and risks.**

- **`#sim-traffic` and #115 are on `main`** (pass 4). The stack is based on `main` at `90dd0ae`.
  The nest element follows the `Vehicle` pattern (oneof field 8, a `validate_nests()` submodule,
  a Python module beside `vehicles.py`). Nests avoid water (`water.rs` / `water.py`). The
  scene-builder subagent skill (`agent/skills/building-a-simulation-scene/SKILL.md`) learns nests.
- **Real SAM in the agent process** is blocked by `todo/2026-11-03-agent-cli-sam-flags.md`
  (`--sam-fake` required). Per-drone segmentation is built against the SAM detector seam and
  proven with the fake.
- **Code issues:** `private-reach-agent-tools-workspace` (`DemoWorkspace._start` reaches into
  `surmap.demo.runs`) and `oversized-file-demo-server` (1750 lines). New live-ingest code must not
  land in `demo/server.py` or route through `DemoWorkspace` private reach.
- **Browser-only paths** (wasm WebSocket clients) cannot run in CI; at best
  `cargo check --target wasm32-unknown-unknown` (V3) plus a recorded Chrome run (V4).
- **Resource cost:** one RTAB-Map sidecar per drone kept alive.

**Open questions settled by the developer (2026-11-04).**

- Sim-only scope exception: no write path to PX4 or any real flight controller, and the survey
  pipeline stays passive.
- One RTAB-Map session and one segmentation run per drone. Switching pauses the old drone and
  keeps its map.
- Delivered as a PR stack.

## Exploration 1: Bevy sim internals — the single rig, manifest, wire, tests — 2026-11-04

**Agent**: Explore subagent
**Scope**: `examples/bevy-sitl-poc/` (Rust), its CI workflows, the Python mirror of the manifest schema, scope statements repo-wide

### Sequence

1. `find -type f` (excluding target) + `wc -l src/**/*.rs` in the sim root — map the crate
2. Read `src/main.rs`, `src/flight.rs`, `src/rig.rs` — the drone entity, eyes, schedule
3. Read `src/shots.rs`, `src/record.rs`, `src/wire.rs` — CLI, recording, wire format
4. Read `src/scene_manifest.rs`, `src/ui.rs`, `src/calibration.rs` — schema, UI, profile
5. Read `src/world.rs`, `src/scene_manifest/buildings.rs`, `src/scene_manifest/nature.rs` — load/spawn, submodule validators
6. Grep test names in `src/scene_manifest/tests.rs`; summarise `assets/scene.json`; `cat assets/cameras/*.json`
7. Read `src/scene_manifest/tests.rs` 1–250 — test style, fixtures
8. Grep `websocket|ws://|tcp|TcpStream|stdout|postMessage|fetch(` over `src`, `index.html`, `Cargo.toml`; cat `Cargo.toml`, `.cargo/config.toml` — any transport
9. Grep `encode_hello|encode_pair|rig_pose_enu|GroundTruthObject` outside `wire.rs`; cat `index.html`, `README.md`
10. `ls .github/workflows`, `ls src/surmap/simulation`
11. Cat `.github/workflows/bevy-wasm-test.yml`, `bevy-wasm-build.yml`; grep `cargo|bevy|rust` in `ci.yml`
12. Read `bevy_bridge.py` 1–135; outline `bevy_wire.py`
13. Grep `serve_bevy_bridge|BevyStreamSession` repo-wide; grep `/sim/|scenarios/` in `src`
14. Cat `src/surmap/agent/server/sim_routes.py`, `simulation_core.py` 1–120
15. Cat `manifest_checks.py`; read `scenario_manifest.py` 1–240
16. Read `simulation_handlers.py` 213–292; `proto/surmap/agent/v1/simulation_tools.proto` 40–70, 300–360
17. Read `bevy_capture.py`, `bevy_ground_truth.py`, `euroc_export.py`
18. Grep `origin|latitude|gps|geodetic` in sim `src`; read `bevy_capture.py` 48–262, `euroc_export.py` 26–60
19. Grep `no flight control|flight control|autopilot|…` repo-wide — scope statements
20. Read `README.md` 12–25, `AGENTS.md` 128–142, `docs/architecture.md` 12–40; grep `flight` in `docs/simulation/bevy-simulation.md`, read 200–220, 570–640
21. Grep `App::new|MinimalPlugins|World::new|run_system_once|app.update`; `#[cfg(test)] mod` layout + `#[test]` counts
22. Read heads of `sweep_tests.rs`, `realism_tests.rs`, all of `look.rs`
23. Grep `SimTime|elapsed_secs|FixedUpdate|Time<…>`; consumers of `Drone`, `LeftEye`, `RightEye`, `ChaseCam`, `StereoFeeds`, `CameraProfile`
24. Read `actors.rs` `tick_behaviours`/`track_line`, `wildfire.rs` `SimClock`, `wildfire/rain.rs`
25. Grep `TICK_HZ|CLOCK_SLACK_S`; `close_shots.rs` head; `ls src/surmap/docs/todo`
26. Cat `src/surmap/docs/todo/2026-11-03-bevy-live-websocket-stream.md`
27. Which `tests/*.py` reference `bevy-sitl-poc`; `ls tests/fixtures/sim_scenario`; `scenario_store.py` presets
28. `ci.yml` job outline; `scenario_manifest.py` 440–481 (`load_presets`)
29. `bevy_wire.py` 124–188 (decoder); fixture directory listings

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|---|---|---|---|
| find | `-type f` | sim root | 35 top-level `src/*.rs` + submodules; assets `scene.json`, `cameras/*.camera.json`, `fx/`, `species/`, `behaviour/person.figure.json`, `building/**` |
| Grep | `websocket\|ws://\|tcp\|TcpStream\|stdout\|postMessage\|fetch(` | sim `src`, `index.html`, `Cargo.toml` | only `building.rs` `fetch(` (asset helper) — **no transport** |
| Grep | `encode_hello\|encode_pair\|rig_pose_enu\|GroundTruthObject` | sim `src` excl. `wire.rs` | `record.rs:251`, `world.rs:32,84,246-247`, `actors.rs:30,179-182`, `world/models.rs:11,111`; encode_* **unused** |
| Grep | `serve_bevy_bridge\|BevyStreamSession` | `*.py` | `bevy_bridge.py`, `tests/test_bevy_bridge.py` only |
| Grep | `/sim/\|scenarios/` | `src/**/*.py` | `sim_routes.py:1-8,25,82-84`, `simulation_core.py:51`, `agent/__main__.py:80`, `server/app.py:160,258`, `scenario_store.py:5` |
| Grep | `add_element\|AddElement\|ELEMENT_KINDS` | handlers, proto | `simulation_handlers.py:44,93,217-290`; proto `:53`, `:313` |
| Grep | `origin\|latitude\|gps\|geodetic` | sim `src` | no geodetic origin in the sim |
| Grep | `no flight control\|flight control\|autopilot` | repo | `flight.rs:3`, `README.md:18-19`, `AGENTS.md:136`, `docs/architecture.md:19,31-32`, `.agents/skills/product-overview/SKILL.md:9,42`, `tech-stack.md:24`, `modal-cloud/SKILL.md:188`, `HACKATHON.md:5`, `docs/credits-usage.md:4`, `docs/segmentation-benchmark.md:4` |
| Grep | `App::new\|MinimalPlugins\|run_system_once\|app.update` | sim `src` | only `main.rs:87` — no headless App tests |
| Grep | `With<Drone>\|LeftEye\|RightEye\|ChaseCam\|StereoFeeds\|CameraProfile` | sim `src` | `main.rs` 290,313,348–351,363–364; `ui.rs:9,17,148`; `rig.rs:14,59,85,87,104`; `record.rs:24,102,181-182`; `shots.rs:19,143-144`; `wildfire/rain.rs:29` |
| Grep | `TICK_HZ\|CLOCK_SLACK_S` | actors, behaviour | `behaviour.rs:24` `TICK_HZ = 10.0` |
| ls | `src/surmap/docs/todo \| grep bevy` | todo | `bevy-live-websocket-stream`, `bevy-loop-closure-acceptance`, `bevy-visual-checkpoints-v3-v5` |

### Inspected files

#### `examples/bevy-sitl-poc/src/main.rs`

**Why**: the drone entity and schedule.
**Excerpt** (52–72, 145–170, 198–252, 347–360):

```rust
#[derive(Component)] struct Drone;      // unit markers, no id
#[derive(Component)] struct LeftEye;  #[derive(Component)] struct RightEye;  #[derive(Component)] struct ChaseCam;
#[derive(Resource)] struct Flight { engaged: bool, yaw_deg: f32, scattered: bool }   // one per app

.add_systems(Startup, (start_loading, setup_drone, setup_cameras, setup_overview, close_shots::setup_close_shots).chain())
// Update: read_controls, takeoff_button, fly_scripted, follow_drone_rig.after(fly_scripted),
//         chase_camera.after(fly_scripted), record::record_frames.after(fly_scripted).after(actors::tick_behaviours)
// FixedUpdate: apply_thrust

let body_kind = match mode.flight {
    FlightMode::Manual => RigidBody::Dynamic,
    FlightMode::SurveyLoop => RigidBody::KinematicPositionBased,
};

// follow_drone_rig: drone.single(), left.single_mut(), right.single_mut()
let local = rig.mount_offset() + rig.mount_rotation() * rig.eye_translation_m(right_eye);
eye.translation = body.translation + body.rotation * local;
eye.rotation = body.rotation * rig.mount_rotation();
```

Eyes are top-level cameras re-posed each frame, not children of the drone. `StereoFeeds { left, right }` is one global resource.

#### `src/flight.rs`

**Why**: the scripted flight.
**Excerpt**:

```rust
//! Scripted `survey-loop` flight: a deterministic kinematic loop over the
//! block, so a capture can be recorded again and give the same frames.
//! It moves the simulation's own drone; SurMap has no flight control.
pub struct FlightPose { pub position: Vec3, /* Bevy */ pub yaw_rad: f32 /* 0 = -z = north */ }
const SPEED_M_S: f32 = 1.5;  MAX_SPEED_M_S = 2.0;  MAX_YAW_RATE_RAD_S = 30°/s
pub fn disaster_block() -> SurveyLoop   // only constructor; route hard-coded
pub fn pose_at(&self, t_s: f32) -> FlightPose   // pure, periodic; altitude 7 + 1.5 sin
```

Tests (144–227): determinism, loop closes, speed ≤ 2 m/s, yaw rate ≤ 30°/s, altitude 4–12 m, distance ≥ 40 m — pure functions sampled every 0.1 s.

#### `src/rig.rs`

**Why**: stereo eyes. `spawn_rig` runs once (returns if `CameraProfile` exists), builds `left`/`right` image targets, two `Camera { order: 1 }` with `CalibratedProjection`, then `insert_resource(StereoFeeds { left, right }); insert_resource(profile.clone())` — one profile, one pair.

#### `src/shots.rs`

**Why**: CLI and scripted flight.
**Excerpt** (139–155):

```rust
let t = sim_time.0.unwrap_or(time.elapsed_secs());
let pose = SurveyLoop::disaster_block().pose_at(t);
let Ok(mut body) = drone.single_mut() else { return };
body.rotation = Quat::from_rotation_y(pose.yaw_rad);
body.translation = pose.position - body.rotation * rig.mount_offset();
```

`RunMode { flight, screenshot, record, camera, scenario }`; flags `--flight survey-loop`, `--screenshot <dir> --at <t>`, `--record <dir> [--frames] [--rate-hz] [--start] [--jpeg] [--colour]`, `--camera`, `--scenario <id>`, `--look-at`. Stills/records force SurveyLoop. wasm reads only `?scenario=` (`page_scenario`, 56–60). `manifest_path` → `scenarios/{id}.json`.

#### `src/record.rs`

**Why**: capture and ground-truth pose.
**Excerpt** (250–251):

```rust
let pose = SurveyLoop::disaster_block().pose_at(t_s);
let pose_enu = wire::rig_pose_enu(pose.position, Quat::from_rotation_y(pose.yaw_rad) * rig.mount_rotation());
```

Lockstep: pin `SimTime`, settle (90 first / 3 per step), GPU `Readback` both eyes, write, advance `t_at(frame+1)`. Writes `camera.json`, `calibration.json`, `ground_truth.json`, `frames.jsonl` (`frame_id,t_ns,left_ref,right_ref,pose_enu[,left_rgb_ref]`), `object_tracks.jsonl`, fire/building jsonl. Pose is recomputed from the script, not read from the entity.

#### `src/wire.rs`

**Why**: wire format. `u32` LE header length + JSON header + (pair) grey8 payloads. `encode_hello(camera, objects)`, `encode_pair(...)` (`pose_enu: [f64;7]`), `rig_pose_enu`. Goldens `tests/fixtures/bevy_sim_wire/{hello,pair}.bin`. `#![allow(dead_code)]` — encode_* never called by the app.

#### `src/scene_manifest.rs` (+ `nature.rs`, `buildings.rs`, `tests.rs`)

**Why**: schema for a new element kind.
**Excerpt** (107–115, 332–379):

```rust
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Element { Box(BoxElement), CollapsedBuilding(CollapsedBuilding), Building(Box<Building>), Person(Person), Vegetation(Vegetation) }
// Element::id() / materials(): exhaustive matches (117–144)
// from_json: version == 1; one id namespace across models/elements/fires/building_fires; materials declared;
// ≤1 scatter; asset paths; validate_weather_fire_vegetation(); validate_buildings(); validate_behaviours()
```

Submodule validators are `impl SceneManifest { pub(super) fn validate_…() }` (`nature.rs:121-154`, `buildings.rs:106-161`, incl. cross-reference checks). `tests.rs`: 30 tests, `every_element_kind_is_declared_in_json`, `the_shipped_scene_manifest_is_valid`, cross-language fixtures `../../tests/fixtures/sim_scenario/*.json`.

#### `src/world.rs`

**Why**: spawn interpreter. `start_loading` loads once; `build_world` runs once; `enu(x,y,z) = Vec3::new(x, z, -y)`.

```rust
match element {
    Element::Box(e) => self.box_element(e),
    Element::CollapsedBuilding(e) => self.collapsed(e),
    Element::Building(e) if !building::is_styled(e, self.districts) => self.building(e),
    Element::Building(_) => {}
    Element::Person(e) => self.person(e),
    Element::Vegetation(_) => {}
}
```

#### `src/ui.rs`

**Why**: on-screen layout. Primary window = `ChaseCam` follow view; right panel 324 px with LEFT/RIGHT `ImageNode`s of `StereoFeeds` (308×231) bound once at `resource_added::<StereoFeeds>`; status line reads `drone.single()`; Take off/Land button toggles `flight.engaged`. No selector, no minimap.

#### Other

- `calibration.rs`: `CameraProfile` (id, model, w/h, fx/fy/cx/cy, distortion, `baseline_m`, `rate_hz`, `mount{forward_m, up_m, pitch_deg}`), a `Resource`.
- `wildfire.rs:165-185`: `SimClock::now() = sim.0.unwrap_or(time.elapsed_secs())`; behaviours tick at fixed `TICK_HZ = 10`.
- `Cargo.toml`: "Browser-only … nothing is sent to a backend"; Bevy 0.18, rapier 0.33; wasm `web-sys` features `Window`, `Location` only.
- `index.html`: banner "Frames stay in this page — nothing is sent to a backend."
- `.github/workflows/bevy-wasm-test.yml`: `cargo test --locked`, path-filtered to `examples/bevy-sitl-poc/**`; `bevy-wasm-build.yml`: `trunk build --release`. `ci.yml`: Python only (+ RTAB-Map/Coral e2e).
- `src/surmap/docs/todo/2026-11-03-bevy-live-websocket-stream.md` (Open, P2): left to do — wasm WebSocket client (`?bridge=ws://127.0.0.1:8773`) sending `encode_hello`/`encode_pair` from eye `Readback` at `rate_hz`, RTAB-Map status overlay, `scripts/serve_bevy_sim.py`. Exists: wire goldens, `BevyStreamSession`/`serve_bevy_bridge` tested over loopback, native `--record`.
- Python: `bevy_bridge.py` (`BevyStreamSession.handle`: hello → backend from `profile_sensor_yaml`; pair → `process_frame` → `BridgeStatus`; `serve_bevy_bridge` via `websockets`); `bevy_wire.py` (`decode_bevy_message` hello/pair, `encode_status`); `bevy_capture.py` (`BevyCapture`: one calibration, one frames tuple); `scenario_manifest.py:60` `ELEMENT_KINDS`, `validate_manifest` 161–212, `add_element` 230–235, `load_presets` 447–481; `simulation_handlers.py:217-281` `_element()` oneof; proto `AddElementRequest` oneof (313–322), `EnuPoint`; `sim_routes.py` serves `/sim/` dist and `/sim/assets/scenarios/<id>.json` (latest version, `no-store`).

### Findings

- **One hard-coded drone.** `Drone` is a unit marker; every system uses `single()`/`single_mut()`; `Flight`, `StereoFeeds`, `CameraProfile`, `Recorder` are global singletons. Eyes are re-posed from the body each frame.
- **Flight is a pure function of time.** `SurveyLoop::pose_at(t)` (deterministic, periodic); the recorder recomputes ground-truth pose from it rather than reading the entity. A per-drone autopilot fits as a pure `pose_at(t, plan)`-style function — the only testable shape, since there is **no headless Bevy App harness**.
- **No inbound channel.** The sim loads the manifest once (no hot reload), reads only CLI args / `?scenario=` / keyboard; the Rust wire is encode-only and unused; `status` (bridge → sim) is never consumed. `Cargo.toml` and `index.html` promise "nothing is sent to a backend". Live tasking therefore needs a new sim ↔ station link; the open `bevy-live-websocket-stream` todo is the same transport for frames.
- **Manifest extension points for `drone_nest`:** `Element` enum + `id()`/`materials()` arms; a `scene_manifest/fleet.rs` validator in the `nature.rs`/`buildings.rs` pattern; a `Builder::element` arm; tests; Python `ELEMENT_KINDS`, `validate_manifest`, `_element()` handler, proto `AddElementRequest` oneof; shared fixtures in `tests/fixtures/sim_scenario/`.
- **Time:** `SimTime`/`SimClock` pin time for stills and lockstep recording; behaviours tick at fixed 10 Hz. A command log stamped in sim time replays deterministically.
- **No geodetic origin** in the sim — local ENU only.
- **Tests:** Rust inline `mod tests` / `tests.rs` files, sentence names, `cargo test --locked` in `bevy-wasm-test.yml` (not in `ci.yml`); cross-language fixtures under `tests/fixtures/`.
- **Scope statements to amend:** `flight.rs:3`, `README.md:17-20`, `AGENTS.md` scope guardrail, `docs/architecture.md` §1 (14–35) and §2.3, `docs/simulation/bevy-simulation.md:213`, `.agents/skills/product-overview/SKILL.md:9,42`, `Cargo.toml` description, `index.html` banner.

## Exploration 2: Python side — agent tools, bridge, RTAB-Map runs, UI, docs, deferred work — 2026-11-04

**Agent**: Explore subagent
**Scope**: `src/surmap/agent/`, `proto/surmap/agent/v1/`, `src/surmap/simulation/`, `src/surmap/slam/`, `src/surmap/demo/`, `web/agent-chat/`, docs, deferred-work records



All paths are relative to the repo root `/Users/mantasi/.superset/worktrees/surmap/simulation-should-include-69c1a180`. Nothing was modified. There is one untracked file I did not create: `docs/simulation/1-WIP/2026-11-04-drone-fleet-whole-work-initial-discovery.md`, a 9-line skeleton that says "Pending the first exploration pass".

---

### 1. Sequence (chronological)

1. `ls` of `src/surmap/agent/**`, `proto/surmap/agent/v1`, `src/surmap/simulation`, `src/surmap/slam`, `src/surmap/demo`, `web/agent-chat`, the todo, code-issues and deferred-answers folders, and `tests | grep agent|sim|bevy|rtab|slam|demo|scenario`. Purpose: map the layout.
2. `wc -l` over every agent, proto, simulation, slam and demo file plus the three docs and AGENTS.md. Listed `skills/using-the-map`, `web/agent-chat/src/*`, `docs/simulation` and `docs`. Purpose: sizes and the UI layout.
3. Read `src/surmap/agent/contracts.py`, `src/surmap/agent/services.py` and `proto/surmap/agent/v1/simulation_tools.proto`. Purpose: how a proto rpc becomes a tool contract and a mounted module.
4. Read `proto/surmap/agent/v1/execution.proto`. Grepped `rpc |default_execution|^service` over the survey, map, jobs and chat protos. Printed the headers of `survey_tools.proto` and `map_tools.proto`. Purpose: the execution kinds and the full rpc list.
5. Printed `survey_tools.proto` lines 30-110. Grepped for the `RunDemoRequest`, `RunRtabmapRequest`, `RunInfo`, `ShowRouteRequest`, `UpdateRouteRequest` and `MapRoute` messages. Purpose: run identity and the route shapes.
6. Read `agent/tools/port.py`, `agent/tools/simulation_core.py` and `agent/tools/simulation_handlers.py`. Purpose: the servicer pattern.
7. Read `simulation/scenario_store.py`. Outlined `scenario_manifest.py` and read its `validate_manifest` and `camera` handling. Purpose: how manifests are versioned in SQLite.
8. Read `agent/server/app.py` and `agent/server/sim_routes.py`. Purpose: registration, and whether a live channel to the sim exists.
9. Read `agent/server/binding.py` and `agent/runtime/tools.py`. Printed the `routes.py` header and outlined `routes.py`, `hub.py`, `runtime/jobs.py` and `runtime/events.py`. Purpose: tool binding and HTTP routes.
10. Read `runtime/jobs.py` lines 150-304. Grepped `websocket|ws://|live|SimulationRig|bevy` in `src/surmap/agent`, and listed every file under `src/` and the Rust sim that mentions websocket. Purpose: SYNC/ASYNC/DETACH behaviour and any live sim link.
11. Read `simulation/bevy_bridge.py` and `simulation/bevy_wire.py`.
12. Read `simulation/bevy_capture.py`. Printed the header of `bevy_ground_truth.py` and outlined it and `euroc_export.py`.
13. Grepped `serve_bevy_bridge|BevyStreamSession|load_bevy_capture|CaptureRecorder` across `src`, `scripts`, `tests` and `examples`, and listed `scripts/`. Purpose: is the bridge wired into anything.
14. Read `src/surmap/docs/todo/2026-11-03-bevy-live-websocket-stream.md` and the head of `tests/test_bevy_sim_rtabmap_e2e.py` (plus lines 140-200).
15. Read the header of `slam/streaming.py` and outlined streaming, sidecar, rtabmap, base, stream_process and stream_outbox.
16. Read `slam/streaming.py` lines 192-361 and 560-603, and the `stream_protocol.py` header and `encode_hello`.
17. Grepped `database|.db|IncrementalMemory|multi.session|pause|resume|DatabasePath` in `src/surmap/slam` and `deploy/rtabmap-stream`. Then grepped and read `deploy/rtabmap-stream/main.cpp` lines 440-630. Purpose: session persistence and multi-session support.
18. Read `slam/sidecar.py` lines 300-380 (how the batch sidecar uses `rtabmap.db`).
19. Read the header and outline of `demo/runs.py`, then lines 60-370.
20. Read `demo/playback.py`. Outlined `demo/server.py`, then read lines 863-1237 (`DemoPlayer`), the module doc (1-60), the GET/POST routes (1488-1666) and `_serve` (1720-1754). Read the `demo/events.py` header.
21. Grepped the `CREATE TABLE`, `create_run`, `finish_run`, `record_source` and `get_run` lines in `demo/history.py`. Read the headers of `run_archive.py` and `replay.py`.
22. Outlined `agent/tools/workspace.py` and read lines 75-116 and 117-461.
23. Grepped `bevy|sim|euroc` in `demo/datasets.py` and `gallery.py`, and grepped the `handlers.py` `run_demo` and `RunBusy` mapping.
24. Read the head of `agent/tools/map_handlers.py`, `MapSceneStore`, `show_route` and `update_route`.
25. Grepped the web UI for `scenario|/sim|revision|getMapScene|iframe|bevy|simulation|MapScene` and read `README.md`.
26. Read `web/agent-chat/src/ChatPage.tsx` lines 30-110 and 200-260, and grepped `ToolStep`/`FrameImage`.
27. Grepped `examples/bevy-sitl-poc/src` for `scenario=|scenarios/|bridge=` (`shots.rs`) and listed `src/`.
28. Grepped `docs/agent.md` for `passive|vehicle|flight|command|route|never…`, then read lines 1-80 and 170-275.
29. Grepped `docs/agent.md` for `architecture|read/run`, and listed the `docs/architecture.md` headings.
30. Read `docs/architecture.md` lines 1-96, 250-272, 456-470 and 535-549, and `docs/agent.md` lines 105-115.
31. Grepped `docs/architecture.md` and `docs/simulation/bevy-simulation.md` for passive/flight/command terms, then read the bevy doc's lines 1-40, 62-73, 200-220, 537-640 and its headings.
32. Read AGENTS.md lines 130-139. Grepped every passive assertion across `proto`, `src/surmap/agent`, `src/surmap/simulation`, the simulation docs and the skill file.
33. Read the head of `skills/using-the-map/SKILL.md` and `simulation/__init__.py`, and listed `docs/simulation/1-WIP` and `docs/simulation/changelog`.
34. Looked at the existing WIP skeleton and `git status`.
35. Printed the title, status and packages of every todo, code-issue and deferred-answer record.
36. Read the relevant records in full (listed in §5).
37. Read the `demo/remote.py` header. Grepped for `multi-drone|fleet|nest` across the docs.
38. Read the head of `tests/test_agent_simulation_tools.py`, listed the fakes, read the head of `tests/agent_tool_fakes.py`, outlined `sim_fakes`, `agent_tool_fakes`, `agent_server_fakes` and `agent_fakes`, and read the head of `test_sim_scenario_e2e.py`.
39. Read `tests/test_bevy_bridge.py` lines 1-80 and 180-210, and listed the bevy fixtures.
40. Read the `scripts/gen_agent_rpc.py` header, grepped tests that reference agent.md, and listed the test names in `test_agent_contracts.py`.
41. Listed the generated web code and `buf.gen.yaml`, and grepped the CLI's `--sim-*` flags in `agent/__main__.py`.
42. Read the `package.json` gen script and `ports.ts` lines 80-140, and listed `e2e/`.
43. Grepped `demo/page.py` for its EventSource use. Read `make_demo_server` (1272-1300, 1395-1425).
44. Read the `tests/conftest.py` head, the pyproject `asyncio_mode`, `ToolRig`/`a_tool_rig` and `EmptyWorkspace`.
45. Read the `docs/agent.md` headings and the Chat UI section (690-720), the bindings section (292-304), jobs and notices (350-363), and `hub.py` lines 186-206.

---

### 2. Inspected files

#### 2.1 Agent tool architecture

**`src/surmap/agent/contracts.py`**: turns proto descriptors into `ToolContract`s.
- `tool_contracts(service_descriptor)` (line 108) gives one contract per rpc. It raises `ValueError` if any rpc lacks `default_execution` (lines 114-119).
- The name is the rpc name in snake_case (`_snake_case`, line 162). The description is the rpc's leading comment, read from the checked-in `agent_descriptor_set.binpb` (lines 277-304). The input schema is the request message as JSON Schema 2020-12, with an optional `execution` property added (lines 196-201).
- A proto3 singular field without presence is *required* in the schema (lines 221-224). Use `optional` for fields the model may omit.
- `*_UNSPECIFIED` enum values are dropped from the offered choices (lines 257-260).
- `resolve_execution(contract, arguments)` (line 123) merges a per-call `execution: {mode, timeout_s, on_timeout}` override over the default.

**`proto/surmap/agent/v1/execution.proto`**:
```proto
enum ExecutionMode { EXECUTION_MODE_UNSPECIFIED = 0; SYNC = 1; ASYNC = 2; }   // 17-23
enum OnTimeout { ON_TIMEOUT_UNSPECIFIED = 0; FAIL = 1; DETACH = 2; }         // 26-32
extend google.protobuf.MethodOptions { ExecutionPolicy default_execution = 51001; }  // 69-72
```
The docs notation "SYNC · 10 s · FAIL" is `option (default_execution) = {mode: SYNC timeout_s: 10 on_timeout: FAIL};` on each rpc.

**`src/surmap/agent/services.py`**: `survey_tools_module`, `map_tools_module`, `simulation_tools_module`, `agent_jobs_module` and `chat_service_module` (lines 40-62) each wrap `_module(descriptor, handlers)`. An rpc with no handler answers `UNIMPLEMENTED` (lines 65-95). A handler named for an rpc the service lacks is a mount-time `CompositionError`.

**`proto/surmap/agent/v1/simulation_tools.proto`**:
- The header comment (lines 7-15) ends: "These tools build a simulated world only; nothing here commands a vehicle (docs/architecture.md §1)."
- 21 rpcs, every one SYNC · 10 s · FAIL except `SearchAssets` (SYNC 20 FAIL) and `DownloadAsset` (SYNC 60 DETACH).
- Positions are `EnuPoint {east, north, up}` (lines 167-171).
- `ScenarioInfo` (lines 453-464) carries `id, name, version, manifest_json, credits, url, updated_at`.
- Nothing about cameras, rigs, vehicles or trajectories.

**`proto/surmap/agent/v1/survey_tools.proto`**:
- Header (lines 14-15): "Passive survey only (docs/architecture.md section 1): these tools launch demos and replays and read their results; none commands a vehicle."
- `RunDemo` and `RunRtabmap` are SYNC 30 DETACH (lines 34-36 and 94-96). `PromptSam` and `RunSamOnDataset` are SYNC 60 DETACH. `ListOnboardModels` is SYNC 10 FAIL (line 28).
- `RunDemoRequest {dataset, optional prompt, optional max_frames, optional fps, optional onboard_model}` (lines 183-195).
- `RunRtabmapRequest {dataset, max_frames?, fps?, onboard_model?}` (lines 555-565).
- `RunInfo {run_id, dataset, prompt, frames, objects, Status{RUNNING, FINISHED, CANCELLED, FAILED}, onboard_model}` (lines 198-226).
- Every run input is a `dataset` id from the catalogue. There is no stream or session input.

**`proto/surmap/agent/v1/map_tools.proto`**:
- Header (lines 14-16): "Passive survey only (docs/architecture.md section 1): these tools edit a display scene and move its camera; none commands a vehicle, and a route here is a drawn path, never a flight plan."
- `ShowRoute`, `UpdateRoute` and `ClearRoute` are SYNC 10 FAIL (lines 55-67).
- `MapRoute {id, name, repeated GeoPoint waypoints, color}` (lines 127-136) uses lon/lat GeoPoints, not ENU.
- `ShowRouteRequest {optional scene_id, optional route_id, name, waypoints, optional color}` (lines 276-287).
- `MapRouteResponse {route, uint64 revision}` (lines 289-294).
- `UpdateRouteRequest` (lines 296-307): an empty waypoint list keeps the current path.

**`jobs.proto`**: `WaitForJobs` (SYNC 300 FAIL), `GetJob`, `CancelJob` and `ListJobs` (SYNC 10 FAIL).

**`chat.proto`**: `ChatService` (`StreamTurn`, `WatchConversation`, `Steer`, `CancelTurn`, `ListModels`, `GetConversation`). It is not a tool service: its rpcs carry no `default_execution` (line 13).

**`src/surmap/agent/tools/simulation_core.py`**: `SimulationTooling(store, sources, hits)` (lines 28-34). `blocking(call)` runs the call in a thread and maps `UnknownRecord`→`NOT_FOUND`, `ScenarioInvalid`→`INVALID_ARGUMENT`, and `LicenceRefused`/`AssetSourceError`→`FAILED_PRECONDITION` (lines 37-46). `scenario_url(id)` returns `/sim/?scenario={id}` (line 51). The edit helper:
```python
async def edit_scenario(tooling, scenario_id, edit):            # 66-73
    def apply() -> Scenario:
        current = tooling.store.scenario(scenario_id)
        return tooling.store.save(scenario_id, edit(current))
    return pb.ScenarioResponse(scenario=scenario_info(await blocking(apply)))
```

**`src/surmap/agent/tools/simulation_handlers.py`**: `simulation_tool_handlers(store, sources)` (lines 75-109) binds each async `tool(request, tooling)` into connect's `(request, ctx)` shape, keyed by PascalCase rpc name (`"AddFire": bind(add_fire_tool)`, …). Handlers build manifest dicts from protos. For example, `_element` (lines 217-281) builds `{"kind": "box", "id", "material", "size_m", "position_enu", …}`, and `add_fire_tool` (lines 320-332) builds a fire dict. Each then calls a pure `scenario_manifest` function through `edit_scenario`.

**`src/surmap/simulation/scenario_store.py`**:
- Schema (lines 28-42): tables `assets`, `asset_files`, `scenarios(id, name, version, updated_at)` and `scenario_versions(scenario_id, version, manifest TEXT, created_at)`, with `SCHEMA_VERSION = 1` via `PRAGMA user_version`. The database runs in WAL mode with one connection per call (lines 150-159).
- `create_scenario(name, preset)` (lines 245-263) slugs the id with a `-2`, `-3`… suffix and stores version 1 as the preset JSON.
- `save(scenario_id, manifest)` (lines 265-280) runs `validate_manifest`, then INSERTs version+1 and UPDATEs `scenarios.version`.
- `scenario(id)` (lines 282-300) reads the latest version.
- `history(id)` (lines 307-318) lists the version numbers.
- Credits are derived from the CC BY library assets a manifest references (lines 320-351).

**`src/surmap/simulation/scenario_manifest.py`**:
- Module doc (lines 1-8): "A scenario *is* a scene manifest (examples/bevy-sitl-poc/src/scene_manifest.rs) … Edits here are pure — they return a new manifest — and every result is validated by the same rules the renderer applies."
- `ELEMENT_KINDS = ("box", "collapsed_building", "building", "person", "vegetation")` (line 60).
- `validate_manifest` (lines 161-212) checks version == 1 and that `camera` is a `.camera.json` path (lines 165-167, so there is one camera profile per manifest), unique ids across elements, models, fires and building fires, materials, at most one scatter, weather, models, fires, and `validate_buildings`.
- `_with(manifest, key, items)` (lines 223-227) deep-copies, replaces the list and validates.
- Presets come from `load_presets(assets_dir)` (line 447).
- There is no notion of drones, nests, waypoints or flights in the manifest.

**`src/surmap/agent/server/app.py`**:
- `SYSTEM_PROMPT` (lines 102-130) includes: "Map edits change only what the person sees; routes are drawn paths, never flight plans. You only launch demos and read results; you never command a vehicle." (lines 116-117).
- `AgentServerConfig` (lines 133-166) has `sim_dir`, `sim_assets` (default `examples/bevy-sitl-poc/assets`) and `sim_dist`.
- `build_simulation_rig` (lines 173-192) returns None when `sim_assets/scene.json` is missing. It builds the `ScenarioStore` at `<cache>/simulation/simulation.sqlite` and the sources.
- `build_demo_workspace` (lines 214-234) calls `make_demo_server(None, …, port=0, with_rtabmap=False, sam_fake=True)`, a non-serving `DemoRunHost`, and wraps it in `DemoWorkspace`.
- Registration in `build_agent_description` (lines 245-315):
```python
sim_handlers = dict(simulation_tool_handlers(simulation.store, simulation.sources)) if simulation is not None else {}
rpc_handlers = {**survey_only, **map_handlers, **sim_handlers}
contracts = (*tool_contracts(_SURVEY_TOOLS), *tool_contracts(_MAP_TOOLS),
             *(tool_contracts(_SIMULATION_TOOLS) if simulation is not None else ()),
             *tool_contracts(_AGENT_JOBS))
hub = ChatHub(..., tools=lambda runner: (*agent_tools(contracts, rpc_handlers, runner), *skill_tools(catalogue, runner)), ...)
services=(survey_tools_module(...), map_tools_module(...), *(simulation_tools_module(...),) ..., agent_jobs_module(...), chat_service_module(...))
```
- The handler dict is keyed only by rpc *method name* across services, so a new service's rpc names must not collide.
- `MapSceneStore()` is constructed once per server (line 272).

**`src/surmap/agent/server/binding.py`**:
- `_HANDLER_SERVICES = (_SURVEY_SERVICE, _MAP_SERVICE, _SIMULATION_SERVICE)` (line 37). A new tool service must be added here, or its contracts are skipped (`if contract.service not in _HANDLER_SERVICES: continue`, lines 68-70).
- `_tool_handler` (lines 87-95) runs `ParseDict(arguments, request_type())`, then `await handler(request, None)`. The response becomes JSON through `MessageToDict(preserving_proto_field_name=True, always_print_fields_with_no_presence=True)`.
- A `bytes image` field becomes a `ToolImage` (lines 98-110). This is how a "camera snapshot of the active drone" tool could return a picture.

**`src/surmap/agent/runtime/tools.py`**: `BoundTool.prepare` and `run` go through `JobRunner.call(contract, arguments, handler, policy=…)` (lines 66-79). The four job tools are at lines 93-117.

**`src/surmap/agent/runtime/jobs.py`**: `JobRunner.call` (lines 169-213):
- ASYNC detaches immediately (line 184).
- SYNC waits `timeout_s * timeout_scale`, then either DETACHes (line 207) or FAILs and cancels the task (lines 208-213).
- `_finish` (lines 280-296) queues a `JobNotice` for detached jobs.
- Job ids are `j-<n>` per runner, and there is one `JobRunner` per conversation. `hub.py` `_job_turns` (lines 188-195) starts a `job_event` turn when a detached job ends while idle. This is the existing mechanism a long "fly this route" job could use to report arrival.

**`src/surmap/agent/server/sim_routes.py`**:
- `SimulationRig(store, sources, static_assets, page_dist)` (lines 41-53).
- `serve_simulation` (lines 79-101) serves `/sim/assets/scenarios/<id>.json` (latest manifest, `cache-control: no-store`), `/sim/assets/library/…`, `/sim/assets/…` and the built page.
- It is HTTP GET only. There is no WebSocket and no push.

**`src/surmap/agent/server/routes.py`**: `/health`, `/geometry/<run>/<object>.glb`, `/frames/<run>/<frame>.jpg` (with `crop` and `max_side`), dataset thumbnails, CORS, and `/sim/` delegated (lines 1-12, 71-120).

**`src/surmap/agent/tools/port.py`**: the `SurveyWorkspace` Protocol (lines 159-265): `scenes`, `datasets`, `prepare_dataset`, `onboard_models`, `run_rtabmap`, `run_sam_on_dataset`, `run_demo`, `run`, `timeline`, `detect`, `objects`, `object_box`, `frame` and `publish_geometry`. Its doc (lines 7-8): "Read/run only (docs/architecture.md section 1): a workspace launches demo runs and reads their results; nothing here commands a vehicle or writes into RTAB-Map's map." `RunInfo` is defined at lines 84-95 and `RunBusy` at line 155.

**`src/surmap/agent/tools/workspace.py`** (`DemoWorkspace`):
- `run_rtabmap` (lines 173-195) overrides `{"with_rtabmap": True, "sam_source": None, "sam_streamer": None}`.
- `run_demo` (lines 250-267) and `_run_recorded` (lines 269-312) start the run through `_start`, await `engine.done`, and stop the engine on cancel.
- `_start` (lines 434-458) calls the private `self._host._take_over(lambda: _RunEngine(...))`, which has an open code-issue record.
- `run()` (lines 314-326) builds `RunInfo` from the history row. The prompt and on-board model are parsed back out of the run **title** (lines 75-115, `_SAM_TITLE`, `_ONBOARD_TITLE`).

**`src/surmap/agent/tools/map_handlers.py`**:
- Doc (lines 8-9): "A scene is display state only: placed GLB shapes, the camera, and drawn route paths."
- `MapSceneStore` (lines 81-103) is in-memory and keyed by `scene_id` (`default`).
- `show_route` (lines 236-250) stores a `pb.MapRoute` and returns `revision=_bump(scene)`.
- `update_route` (lines 253-270) replaces the name, waypoints or colour.
- `clear_route` (lines 273-278) removes the route.

**`scripts/gen_agent_rpc.py`**: `PROTOS = ("execution", "survey_tools", "jobs", "chat", "map_tools", "simulation_tools")` (line 28). A new `.proto` must be appended here. Command: `uv run --with grpcio-tools==1.73.1 python scripts/gen_agent_rpc.py`, and the docs add `git diff --exit-code src/surmap/agent/proto` (`docs/agent.md` lines 292-302).

#### 2.2 Simulation bridge

**`src/surmap/simulation/bevy_wire.py`**:
- Doc (lines 1-5): "Every message is a little-endian `u32` header length, a compact JSON header, then (pairs only) the left and right grey8 payloads."
- `BevyHello(camera: CameraProfile, objects: tuple[GroundTruthBox, ...])` (lines 29-32).
- `BevyPair(frame_id, t_ns, width, height, encoding, pose_enu: Pose, left_data, right_data)` (lines 35-44).
- `decode_bevy_message` (lines 124-141) handles `type` ∈ {`hello`, `pair`} only.
- `encode_status` (lines 56-67) emits `{"type": "status", frames, posed, lost, keyframes, dropped}`.
- **There is no drone id, rig id or session id field anywhere in the wire format.**

**`src/surmap/simulation/bevy_bridge.py`**:
- `BevyStreamSession` (lines 54-118) handles one hello (camera), then builds one backend via `backend_factory(cam0_yaml=…, cam1_yaml=…, width, height)` (lines 70-79). Each pair goes to `recorder.record_pair` and `backend.process_frame(StereoFramePair(... left_data=_png(...)))`, then the session polls updates and returns a `BridgeStatus`. A pair before the hello raises `BevyWireError("pair received before any hello")` (line 81). `close()` closes the backend and calls `recorder.finish()`.
- `serve_bevy_bridge(host, port, session_factory)` (lines 121-135) gives one `BevyStreamSession` per WebSocket connection. The session is closed when the socket ends.
- So the shape is one stream = one connection = one camera rig = one RTAB-Map backend. There is no pause or resume; closing the socket closes the backend.
- The `StreamingBackend` Protocol is at lines 25-36 and `PairRecorder` at lines 39-42.

**`src/surmap/simulation/bevy_capture.py`**:
- `CaptureRecorder(root, calibration, objects)` (lines 48-141) buffers pairs in memory. `finish()` writes `calibration.json`, `ground_truth.json`, `frames/{left,right}/<t_ns>.png` and `frames.jsonl` (with `pose_enu` and refs), then `export_euroc_session(root / "euroc", frames, cal)` (line 141).
- `load_bevy_capture(root)` (lines 177-262) returns a `BevyCapture(calibration, objects, frames, camera, fire_perimeters, object_tracks, wind, building_fires)`.

**`src/surmap/simulation/euroc_export.py`**: `export_euroc_session(output_dir, frames, calibration, gps=())` (line 26) returns an `ExportResult(root, pair_count, gps_count)`.

**`src/surmap/simulation/bevy_ground_truth.py`**: `left_eye_optical_pose(rig, calibration)` (line 88), `project_box` (line 144) and `box_surface_distance` (line 182).

**Who uses the bridge**: only `tests/test_bevy_bridge.py`. No script or server starts `serve_bevy_bridge`. `load_bevy_capture` is used by `scripts/score_sim_detections.py`, `simulation/detection_eval.py` and the tests.

**`tests/test_bevy_sim_rtabmap_e2e.py`**: lines 152-200 show how a capture becomes an RTAB-Map session today. It builds a `StreamingRtabmapBackend(cam0_yaml=profile_sensor_yaml(profile, 0), …, region_buffer_s=1e6, dense_journal=True)` directly and feeds `capture.frames` in lockstep. It does **not** go through `DemoPlayer`, `DatasetSpec` or the run history.

#### 2.3 RTAB-Map and segmentation runs

**`src/surmap/slam/streaming.py`**:
- Doc (lines 1-8): a long-lived sidecar over stdin/stdout. `process_frame` never waits: frames go into a bounded drop-oldest queue (`queue_size=4`, line 206).
- Constructor (lines 195-311): a docker container `surmap-rtabmap-stream-<uuid12>`, or a `native_binary`. It sends `encode_hello(...)` and waits up to 30 s for `ready`.
- `flush()` (lines 565-585) closes stdin and waits for the final graph. `close()` (lines 586-603) terminates and `docker rm -f`.
- No database path, save, load, pause or session parameters exist.

**`deploy/rtabmap-stream/main.cpp`**:
```cpp
rtabmap::Odometry* odom = rtabmap::Odometry::create(params);   // 466
rtabmap::Rtabmap slam;
slam.init(params, "", false);                                   // 468: empty database path → in-memory, nothing persisted
...
if (!readFramed(pairHeader)) break;  // EOF: finalize below    // 487
...
emitGraph(slam, true); delete odom; return 0;                   // 621-623
```
- One process is one in-memory map. EOF finalises it, and the map dies with the process. There is no multi-session, database reuse or append.
- The only control message type besides pairs is `region` (line 490).

**`src/surmap/slam/sidecar.py`** (batch): runs `rtabmap-euroc_dataset --output /data --output_name rtabmap /data`, then `rtabmap-export … /data/rtabmap.db` (lines 340-377). This does produce an `rtabmap.db`, but only offline over a finished EuRoC dataset. It has no resume or append either.

**`src/surmap/slam/stream_protocol.py`**: `PROTOCOL_VERSION = 5` (line 22). `encode_hello(cam0_yaml, cam1_yaml, width, height, params, max_depth_m, region_buffer_s, min_disparity_px, dense_journal)` is at lines 107-136.

**`src/surmap/demo/playback.py`**: `PlaybackControls` offers `pause()`, `resume()`, `cancel()` and `wait_while_paused(timeout)` (lines 9-40) on a `threading.Event`.

**`src/surmap/demo/server.py`** (`DemoPlayer`, lines 863-1234):
- Input is always a `PreparedDataset`: `timestamps = prepared.timestamps_ns[...]` (line 1029), with JPEGs read from disk (`_display_jpeg`, lines 1081-1082). **There is no live-stream input.**
- `_backend()` (lines 989-1017) picks the injected `backend_factory`, else `RemoteCm5Backend` (with `cm5_host`), else `StreamingRtabmapBackend` (live) or `SidecarRtabmapBackend` (batch).
- Pause (lines 1071-1079): "Paused: no pairs reach SLAM and no new frames are shown, but held frames keep resolving as their odometry lands." The backend stays alive while paused. That is the only "pause with map kept" behaviour that exists, and it holds only within one run and one process.
- SAM is attached per run as `sam_source`/`sam_detector` (`_SamWorker`) or `sam_streamer` (`_SamStreamWorker`) (lines 1038-1050). The on-board detector is `detection_source` (`_DetectionWorker`).
- At the end, `backend.flush()`, a `final` event, then `backend.close()` in `finally` (lines 1140-1234).

**`src/surmap/demo/runs.py`**:
- `_RunEngine` (lines 32-213) runs one player thread. It subscribes renderers through queues with drop-stalest. `start()` calls `store.create_run(dataset_id, title)`, which gives a new uuid run_id (line 76). `_record` persists events (lines 142-183). `_play` ends with `finish_run(run_id, "completed" | "interrupted")` (lines 205-206).
- `DemoRunHost` holds a **single** `run_engine` and `current` (lines 249-269).
- `_take_over` (lines 343-365) stops the previous engine and waits `TAKEOVER_TIMEOUT_S = 10.0` (line 237). **Only one run per host at a time; a new run cancels the old.**
- `start_run(prepared, sam_prompt, *, sam_from=None)` is at lines 271-308. `start_replay(run_id, speed, record)` (lines 310-341) uses `JournalPlayer`.

**`src/surmap/demo/history.py`** (`RunHistoryStore`):
- Tables (lines 64-137): `runs(run_id, dataset_id, title, total_frames, status, created_at, finished_at)`, `frames`, `maps`, `detections`, `surface_points`, `events`, `run_rigs`, `dense_frames` and `run_sources(run_id, source_run_id)`.
- `create_run` (line 173) gives `uuid4().hex[:16]`. `record_source` is at line 430 and `finish_run` at line 474.
- There is no "append to an existing run" operation.

**`src/surmap/demo/events.py`**: `DemoEvent(kind, data, jpeg)`. The kinds are frame, status, final, map, detections, sam, region, surface, plus the journal-only rig and dense (lines 50-56).

**`src/surmap/demo/replay.py`**: replays a journal with no RTAB-Map and no SAM. Regions are recomputed from the journalled dense buffer.

**`src/surmap/demo/run_archive.py`**: `.surmaprun` is a gzipped SQLite export of one run plus its replay lineage. "A run still recording cannot be exported."

**`src/surmap/demo/remote.py`**: `RemoteCm5Backend`, a `LiveSlamBackend` over `StreamSurvey` (Connect over WebSocket), is the only existing *live* stream path into RTAB-Map. It is still driven by `DemoPlayer` playing a prepared dataset.

**Demo HTTP** (`server.py`):
- `/stream?dataset=…`, `?replay=`, `?rebuild_rtabmap=` are SSE (`_serve`, lines 1720-1751). `frame` and `sam` events carry `image_b64`.
- `POST /control {action: pause|resume|cloud_*}` acts on `server.current` (lines 1604-1626).
- `demo/page.py` uses `new EventSource('/stream?dataset=…')` (line 556) and listens for `frame`, `map`, `sam` and `final` (lines 484-524). **The camera feed shown to a user today is this demo page's `frame` events.**

#### 2.4 UI

**`web/agent-chat/src/ChatPage.tsx`**:
- It polls the map scene (lines 67-84):
```tsx
// The map scene lives server-side and the agent edits it mid-turn; poll it so
// placements, moves, camera navigation and routes appear without a reload.
port.getMapScene().then((scene) => { if (current) setMapScene((prev) => (prev?.revision === scene.revision ? prev : scene)); }, ...);
const timer = window.setInterval(poll, 2000);
```
- Layout (lines 238-250): `MapPane`, `Transcript`, `JobsPanel`, `Composer`, plus a Dataset gallery screen. **There is no sim view, camera-feed pane or iframe to `/sim/`.**

**`web/agent-chat/src/ports.ts`**: `MapSceneView {sceneId, revision, camera, objects, routes, layers}` (lines 104-111). `ChatPort.getMapScene()` (line 134) has no scenario or sim method.

**`web/agent-chat/src/gen/surmap/agent/v1/`** contains `chat_pb.ts`, `execution_pb.ts`, `jobs_pb.ts`, `map_tools_pb.ts` and `survey_tools_pb.ts`. **There is no `simulation_tools_pb.ts`**, although `yarn gen` runs `buf generate ../../proto --path ../../proto/surmap/agent/v1`. The UI does not use SimulationTools.

**Tool images**: `ToolStep.tsx:55` → `FrameImage.tsx` (a data URL), shown inline in the transcript.

**Sim page scenario load**: `examples/bevy-sitl-poc/src/shots.rs` lines 40-59. It reads `?scenario=<id>` once from `window.location.search` and fetches `scenarios/{id}.json`. No grep hits for any reload or poll. The agent's scenario version bumps reach the page only on a reload.

#### 2.5 Docs (passive and no-flight-control statements)

**`docs/architecture.md`**:
- L1: "# SurMap architecture — passive survey"
- L14: "SurMap is a passive payload."
- L17-28 (scope table): OUT OF SCOPE (deferred) lists "flight control of any kind" (L19), "autonomous navigation" (L20), "path planning / obstacle avoidance" (L23), "mission orchestration / tasking" (L25) and "route replanning" (L26).
- L31: "The drone is flown manually or by a separate, existing autopilot."
- L32-33: "SurMap has no write path to any flight controller: no actuator, waypoint, or velocity commands exist in any interface below."
- L34-36: "RTAB-Map runs passively on-board: it estimates the camera trajectory so point clouds can be registered into one map. Its output is never fed back as a control signal."
- L62 (§2.2): "Consumes survey data only; issues no commands to the drone."
- §2.3 Machine 3 — simulation (L64-84):
  - L68-71: "Contract: whatever this machine produces must be indistinguishable in format from a recorded real session (§5), so base-station code cannot tell simulation from flight data."
  - L75-76: "SurMap stays passive — PX4 (or a human) flies; no package publishes flight commands."
  - L83-84: "Where those PX4 notes say the vehicle is armed, that is PX4's motor-enable state. SurMap does not set it."
  - §2.3 does not mention Bevy at all.
- L255-256: "One drone's footage at a time in this phase. Multi-drone map merging is a later design problem."
- §4.3 L262: "No other component may have a simulation-only code path." L269-270: "Loading that file does not command the vehicle."
- §10 L460: "Payload control only — nothing flight-related." L466-467: "Both APIs are payload/data APIs. Adding any flight-command endpoint would be a scope change, not an extension."
- §11 L537-543: "Revisit only after the passive pipeline works end to end on real footage: 1. Autonomous navigation and SLAM-based steering … 2. Flight-controller integration of any kind. 3. Base-station orchestration: tasking drones, replanning routes from the semantic map, closing the observe → decide → fly loop. 4. Multi-drone concurrent survey and map merging." Also 6: "LLM mission-level decision-making (the LLM here only labels what was observed)."

**`docs/agent.md`**:
- L112: "…publishes GLB through a `GeometryStore` (`tools/geometry.py`). Read/run only."
- L181-182: "drawn route paths (display only — never a flight plan)."
- L290 (skills table): "drawing routes (drawn paths, never flight plans)".
- The tool catalogue is at L21-74, in the format `| tool | Service.Rpc | SYNC · 10 s · FAIL |`. A fleet section would be added there and in a new section next to "Simulation tools" (L197-262).

**`docs/simulation/bevy-simulation.md`**:
- L212-213: "Moving people are layered ground truth for the survey; they are never written into the static scene or RTAB-Map's map ([architecture.md](../architecture.md) §1), and nothing here moves the drone."
- L581-582: "`--flight survey-loop` flies the deterministic rounded-rectangle loop over the block (1.5 m/s, 7 ± 1.5 m up, ≤ 10.7 °/s yaw, 182 m, 121 s)".
- L611-614: "Browser → RTAB-Map: the wire format … and the Python bridge (`surmap.simulation.bevy_bridge`) exist and are tested; the wasm WebSocket client is not built yet".
- L537-551: one stereo rig, "the single source of truth".

**AGENTS.md L133-139**:
> ## Scope guardrail
> Passive survey only (see docs/architecture.md §1): no flight control, navigation, or mission orchestration. Object points are layered onto RTAB-Map's output, never written back into RTAB-Map's internal map, and moving objects are never fused into the static scene.

**Other passive assertions in code and docs that a fleet exception would touch:**
- `proto/surmap/agent/v1/map_tools.proto:14-16`, `survey_tools.proto:14-15` and `simulation_tools.proto:14` ("nothing here commands a vehicle").
- `src/surmap/agent/tools/port.py:7-8`, `workspace.py:7-8` and `onboard.py:7-8`.
- `src/surmap/agent/server/app.py:116-117` (SYSTEM_PROMPT).
- `src/surmap/agent/skills/using-the-map/SKILL.md:9-12`: "A route here is a drawn path, never a flight plan, and no map tool commands a vehicle — if the person asks for flight or navigation of a real vehicle, say the map cannot do that and offer to draw the path instead."
- `src/surmap/simulation/__init__.py:3-5`: "SurMap stays passive: this package never sends flight commands. PX4 (or a human) flies…"
- `docs/simulation/px4-sitl.md:3` and `:32`.

#### 2.6 Tests

- **`tests/test_agent_simulation_tools.py`**: the `a_toolset(tmp_path)` builder (lines 23-35) creates a real `ScenarioStore` on `tmp_path` and canned sources over `RecordingFetch`. `call(handlers, rpc, request)` calls `handler(request, None)` (lines 38-41). Tests are `async def test_<plain-sentence>()` with `# Given / # When / # Then` comments (lines 44-60).
- **`tests/sim_fakes.py`**: `POC_ASSETS` (the real `examples/bevy-sitl-poc/assets`), `RecordingFetch`, and manifest readers `element_ids`, `fire_ids`, `person_ids`, `district_ids`, `building`, `weather_of` and `wind_of`.
- **`tests/agent_tool_fakes.py`**: `a_tool_rig(tmp_path, onboard=)` (lines 69-95) is a real non-serving `make_demo_server(prepared_tiny, port=0, with_rtabmap=False, sam_fake=True, history_store=…)` plus `DemoWorkspace`. Other helpers: `a_recorded_run`, `with_an_object`, `eventually`, `the_run_started_by`, `settled` and `the_run_started_by_the_host`.
- **`tests/agent_server_fakes.py`**: `ChatRig`/`a_chat_rig`, `TurnStream`, `EmptyWorkspace` (a stub `SurveyWorkspace`, line 273) and `NoGlbs`.
- **`tests/agent_fakes.py`**: `ScriptedChatModel`, `tool_call`, `calling`, `answer`, `FakeToolHandler`, `a_tool_contract`, `a_session` and `collect`.
- **`tests/test_sim_scenario_e2e.py`**: a scripted model drives a real turn on `HypercornHost` port 0 over a real SQLite store, then fetches `/sim/assets/…`.
- **`tests/test_bevy_bridge.py`**: `FakeBackend`, `FakeRecorder` and `FakeFactory` (lines 31-80), plus a loopback WebSocket test with the goldens `tests/fixtures/bevy_sim_wire/{hello,pair}.bin`.
- Bevy fixtures: `bevy_capture_dynamics`, `bevy_sim_capture`, `bevy_sim_detector_capture` and `bevy_sim_wire`.
- pyproject: `asyncio_mode = "auto"`, `testpaths = ["tests"]`. `tests/conftest.py` holds a hang-dump watchdog.
- `tests/test_agent_contracts.py` checks every rpc is a snake_case tool with a description and its declared default execution.

---

### 3. Grep and glob

| Pattern | Scope | Notable hits |
|---|---|---|
| `rpc \|default_execution\|^service` | agent protos | full rpc lists (see §2.1); `chat.proto:13` says it is not a tool service |
| `websocket\|ws://\|SimulationRig\|bevy` | `src/surmap/agent` | only `app.py:157-190` (`sim_assets`, `build_simulation_rig`), `sim_routes.py`, `routes.py:22,77`, `__main__.py:77`. **No websocket in the agent package** |
| files with `websocket` | `src/`, sim `src` | `demo/remote.py`, `simulation/bevy_bridge.py`, `survey/{ws_client,station_main,modal_hosting,modal_station_app,cm5_main}.py`, the todo `2026-11-03-bevy-live-websocket-stream.md`, changeset `2026-11-03-survey-websocket-modal-hosting.md` |
| `serve_bevy_bridge\|BevyStreamSession\|load_bevy_capture\|CaptureRecorder` | src, scripts, tests | bridge used only in `tests/test_bevy_bridge.py:14,82-86,187-188`; capture in `scripts/score_sim_detections.py:21,47`, `simulation/detection_eval.py:26` and four tests |
| `database\|.db\|IncrementalMemory\|pause\|resume\|DatabasePath` | `src/surmap/slam`, `deploy/rtabmap-stream` | only the batch `sidecar.py:318,357-374` (`rtabmap.db`) and `rtabmap.py:70,83` (`database_path` of the native binding). Streaming: none |
| `database\|init(` | `main.cpp` | `:468 slam.init(params, "", false);` |
| `scenario\|/sim\|revision\|getMapScene\|iframe\|bevy` | `web/agent-chat/src`, `e2e` | only map-scene polling (`ChatPage.tsx:41,73-75`, `ports.ts:104-134`, `connect-chat.ts:87-130`). No sim or scenario |
| `scenario=\|scenarios/\|bridge=` | sim `src` | `shots.rs:40,46,55-59,459`. No `bridge=` (the WS client is not built) |
| passive/flight/command terms | `docs/architecture.md` | L1, 14, 19, 25, 31-36, 62, 71, 75-76, 153, 235, 256, 269, 446, 460, 467, 537-543 |
| same | `docs/simulation/bevy-simulation.md` | L213, 581 |
| same | `docs/agent.md` | L112, 139, 181-182, 290 |
| `passive\|never command\|flight plan\|commands a vehicle` | proto, agent, simulation, docs, skill | listed in §2.5 |
| `multi-drone\|fleet\|nest` | docs, `src/surmap/docs` | only `architecture.md:256`, `:543` and the WIP skeleton |
| `bevy\|sim\|euroc` | `demo/datasets.py`, `gallery.py` | only EuRoC and KITTI. **There is no Bevy or sim dataset in the catalogue** |
| `EventSource\|/stream\|/control` | `demo/page.py` | L455, 466, 484-524, 556, 619, 634 |
| `--sim-*` | `agent/__main__.py` | `--sim-dir`, `--sim-assets`, `--sim-dist`; `serve` calls `build_simulation_rig(config)` |

---

### 4. Findings

#### 4.1 How a tool service is defined, end to end

1. **Proto**: write the `.proto` in `proto/surmap/agent/v1/`. Import `execution.proto`. Every rpc needs a leading comment (this becomes the tool description) and `option (default_execution) = {mode: … timeout_s: … on_timeout: …}`. Field comments become argument descriptions. Use `optional` for omittable scalars. Enums need a `*_UNSPECIFIED = 0`.
2. **Codegen**: add the name to `PROTOS` in `scripts/gen_agent_rpc.py:28`, then run it. This writes `_pb2.py`, `.pyi` and the shared `agent_descriptor_set.binpb`, all checked in. Optionally run `yarn gen` for the web UI.
3. **Servicer**: write a handler module of async functions `tool(request, ctx_or_tooling) -> response`, bound by a `*_tool_handlers(...)` factory into `(request, ctx)` closures keyed by rpc name. Failures are `ConnectError(Code.X, msg)`. The examples are `simulation_handlers.py` and `map_handlers.py`.
4. **Module**: add `xxx_module(handlers)` to `services.py`.
5. **Registration**: in `app.py:build_agent_description`, add the handlers to `rpc_handlers`, the contracts to the `contracts` tuple and the module to `services`. In `binding.py:37`, add the service to `_HANDLER_SERVICES`, or the contracts are silently skipped. Rpc names share one dict across services, so they must not collide.
6. **Docs**: rows in the `docs/agent.md` catalogue and a section.
7. **Tests**: handler-level tests with no model and no server (`call(handlers, "Rpc", pb.Req(...))`), an e2e test through `a_chat_rig` or `HypercornHost`, and the contract tests.

#### 4.2 Execution kinds

- **SYNC**: the turn blocks up to `timeout_s`. On timeout it either FAILs (the task is cancelled) or DETACHes (becomes a job and the model gets the handle).
- **ASYNC**: the call detaches at once.
- Detached jobs that end produce a `JobNotice`. While the conversation is idle, that notice starts a `job_event` turn (`hub._job_turns`).
- Jobs belong to one conversation's `JobRunner` (`j-1`, `j-2`, …). They do not persist across processes. Any long-lived per-drone state must live elsewhere, in station-level state like `MapSceneStore` or `ScenarioStore`, not in the job.
- Precedent: long operations are SYNC 30 DETACH (`run_demo`, `run_rtabmap`).

#### 4.3 SimulationTools, MapTools and SurveyTools

- **SimulationTools** edits a scenario manifest. Each edit is a pure function over the manifest dict, then `validate_manifest` (which mirrors `scene_manifest.rs`), then `ScenarioStore.save` writes a new version row in `scenario_versions`. The page fetches the latest version at `/sim/assets/scenarios/<id>.json`.
  - The manifest has exactly one `camera` profile and no drones, nests or flights.
  - Adding nests as a manifest key would need matching changes in `validate_manifest`, `element_ids` and the Rust `scene_manifest.rs`.
- **MapTools** routes are lon/lat display paths in an in-memory `MapSceneStore`. Every change bumps `revision`, and the UI polls it every 2 s. They are not connected to any vehicle.
  - Sim positions are ENU.
  - `surmap.simulation.disaster_world.enu_to_wgs84` exists for the conversion. It is exported from `simulation/__init__.py`, but I did not open it.
- **SurveyTools**: `run_demo`, `run_rtabmap` and `run_sam_on_dataset` all take a *catalogue dataset id*. They go through `DemoWorkspace`, then the `DemoRunHost` single engine, then `DemoPlayer` over a `PreparedDataset` on disk. `list_onboard_models` lists Coral profiles.
  - The agent's own `DemoRunHost` is built non-serving with `with_rtabmap=False`. `run_rtabmap` forces RTAB-Map on per run.
  - Runs started by the agent are recorded in history but not viewable live from the agent server. There is no SSE route on the agent server.

#### 4.4 Is there a live agent→sim channel?

**No.**
- The agent server only serves static manifests and assets over HTTP GET (`sim_routes.py`).
- The sim page reads `?scenario=` once at load (`shots.rs:55-59`). There is no polling, reload, WebSocket or command path.
- The only WebSocket code for the sim is `bevy_bridge.serve_bevy_bridge`. It flows the other way (sim→Python frames, status back) and is started by nothing except a test.
- The wasm client (`?bridge=ws://127.0.0.1:8773`) and `scripts/serve_bevy_sim.py` are open TODO M6.

#### 4.5 Bridge: one stream, one rig

- The wire format has `hello` (camera profile plus ground-truth boxes) and `pair` (frame_id, t_ns, size, encoding, `pose_enu`, grey8 L/R). There is no drone or session id.
- One WebSocket connection is one `BevyStreamSession`, which is one backend from the factory, plus an optional recorder.
- Closing the socket closes the backend and finishes the recorder.
- A capture becomes an RTAB-Map session in one of two ways:
  - `CaptureRecorder.finish()` writes the capture dir and a EuRoC export (`euroc/`). This could feed the batch sidecar, but no catalogue `DatasetSpec` points at it.
  - `load_bevy_capture` → `StreamingRtabmapBackend` directly, as in the e2e test.
- Bevy captures are not runs in `RunHistoryStore`, so `get_run`, `find_objects` and `get_frame` cannot see them.

#### 4.6 RTAB-Map sessions: pause, resume and append

- The streaming sidecar's map is in memory (`slam.init(params, "", false)`). It lives exactly as long as the process. EOF finalises it, and nothing is saved, loaded or appended.
- Pausing is only possible inside one `DemoPlayer` run (`PlaybackControls.pause`): frames stop and the backend stays alive. It is one per host, through `POST /control`.
- `DemoRunHost` allows one running engine. Any new run cancels the previous one (`_take_over`, 10 s timeout, else `RunBusy`→`UNAVAILABLE`).
- Run identity: `RunHistoryStore.create_run` makes a fresh 16-hex uuid per engine. `RunInfo` (proto and port) is `run_id, dataset, prompt, frames, objects, status, onboard_model`. The prompt and onboard model are recovered by parsing the run title.
- There is no "append to an existing run" operation. Only `record_source` links a replay to its source.
- Per-drone persistent maps would need one of three things:
  - several concurrent `StreamingRtabmapBackend` processes (one per drone, each kept alive while paused);
  - an RTAB-Map database path in the sidecar hello, with `Mem/IncrementalMemory` and multi-session support, which the C++ does not have today;
  - several `DemoRunHost`-like engines.
- SAM is attached per `DemoPlayer` as `sam_source`/`sam_detector`/`sam_streamer`, consuming the left display JPEG per frame. `_SamWorker.submit(frame_id, t_ns, jpeg)` is the per-frame seam a live source could reuse.

#### 4.7 UI

- The chat UI shows a MapLibre `MapPane`, which polls `getMapScene` every 2 s and redraws on a `revision` change, plus the transcript, jobs panel and composer.
- It has no sim view or camera feed and no SimulationTools bindings (`simulation_tools_pb.ts` is absent from `src/gen`).
- The only live camera feed in the product is the demo console page: SSE `/stream` `frame` events with `image_b64`, from `demo/server.py` and `page.py`.
- The Bevy page at `/sim/?scenario=` is a separate page with no link from the chat UI.
- Agent scenario edits reach the sim page only through a new version, and the page sees it only on reload. Agent map edits reach the chat UI through the revision bump and the 2 s poll.

#### 4.8 Scope implications (statements a sim-only fleet exception would need to amend)

- `docs/architecture.md`: L14 and L19-26 (scope table), L31-36, L62, L68-71 and L75-76 (§2.3), L255-256, L262 (§4.3 "No other component may have a simulation-only code path", which directly conflicts with sim-only fleet tools), L460 and L466-467 (§10), and L537-543 (§11 items 1, 3 and 4; also 6).
- `docs/agent.md`: L112, L181-182, L290, and the SYSTEM_PROMPT text it mirrors.
- `docs/simulation/bevy-simulation.md`: L212-213.
- AGENTS.md L133-139.
- Proto headers: `map_tools.proto:14-16`, `survey_tools.proto:14-15`, `simulation_tools.proto:13-14`.
- Code docstrings: `port.py:7-8`, `workspace.py:7-8`, `onboard.py:7-8`, `simulation/__init__.py:3-5`.
- `app.py:116-117` (SYSTEM_PROMPT) and `skills/using-the-map/SKILL.md:9-12`.

---

### 5. Deferred-work records

**Listing:**
- `src/surmap/docs/todo/` (21 records):
  - Moving-object set (2026-10-27): `live-ros2-connectrpc-bridge`, `moving-detector-identity-adoption`, `moving-euroc-negative-control`, `moving-governor-wiring-cm5-replay`, `moving-runtime-vo-increments`, `moving-snippet-acceptance-tuning`, `moving-snippet-dataset-spikes`.
  - Agent and sim set (2026-11-03): `agent-cli-sam-flags`, `agent-tool-image-parts`, `bevy-live-websocket-stream`, `bevy-loop-closure-acceptance`, `bevy-visual-checkpoints-v3-v5`, `camera-profile-fisheye-and-render-tests`, `fire-eye-mount-pitch`, `non-agent-clients-on-fake-servers`, `sidecar-odometry-covariance` (fixed in code, PR #103), `streaming-sidecar-lens-models`.
  - Visual set (2026-11-04): `cmu-and-pvc-textures`, `flame-flipbook-resolution`, `legacy-buildings-burn`, `texture-uv-scale-measured`.
- `src/surmap/docs/code-issues/`: `oversized-file-demo-{datasets,page,remote,server}.md`, `private-reach-agent-server-hub.md`, `private-reach-agent-tools-workspace.md`.
- `docs/surmap/deferred-answers/`: `2026-11-03-fireworks-default-models.md` and `2026-11-03-registry-muse-base-url-seam.md`, both "Awaiting review" and not relevant.

**Relevant records, key lines:**
- **`todo/2026-11-03-bevy-live-websocket-stream.md`** (Priority 2, Open, M6): "The wasm WebSocket client (`?bridge=ws://127.0.0.1:8773`) sending `wire::encode_hello` and `encode_pair` from `Readback` of the eye targets at `rate_hz`, the RTAB-Map status overlay from the bridge's replies (visual spec §8), and `scripts/serve_bevy_sim.py` (static `dist/` + `assets/` on one origin, bridge on 8773, `--record`). Then the V4 recorded live run in Chrome." What exists: "Wire format with byte-exact goldens shared by Rust and Python; `BevyStreamSession` and `serve_bevy_bridge` (tested over loopback); the native `--record` path…; the camera profile carried in the hello."
- **`todo/2026-11-03-bevy-loop-closure-acceptance.md`** (Priority 1, Open): a real-sidecar test over the closed 182 m `survey-loop`. "The capture is 73 MB — too large to commit — and CI runners have no GPU to record it."
- **`todo/2026-11-03-sidecar-odometry-covariance.md`**: Fixed in code (PR #103). The streaming sidecar now passes the odometry covariance. The end-to-end proof waits on the loop-closure record.
- **`todo/2026-11-03-bevy-visual-checkpoints-v3-v5.md`**: V5, "the same stills in Chrome/WebGPU (`trunk serve`) for parity with native". The browser runtime is unverified.
- **`todo/2026-11-03-agent-cli-sam-flags.md`**: "`build_demo_workspace` … refuses to start without `--sam-fake`". The agent process cannot run a real SAM yet, which matters for "segmentation of the active drone".
- **`todo/2026-11-03-agent-tool-image-parts.md`**: tool images reach the model only as the placeholder `<image/jpeg, N bytes, shown to the user>`. This matters if the agent is meant to look at the active drone's camera.
- **`todo/2026-10-27-live-ros2-connectrpc-bridge.md`**: a future live stream into `Cm5SurveyService` "without a capture-directory round trip". It is a precedent for live ingest.
- **`code-issues/private-reach-agent-tools-workspace.md`**: "`DemoWorkspace._start` … constructs `_RunEngine` and calls `_take_over` — both private to `surmap.demo.runs`." The proposed fix is `start_run(prepared, sam_prompt, *, player_options: PlayerOptions | None = None)`. Any per-drone run plumbing touches this.
- **`code-issues/oversized-file-demo-server.md`**: `demo/server.py` is about 1750 lines against a 500-line limit. The proposed split is `demo/workers.py`, `display.py`, `floor_plan.py` and `http.py`. New live-ingest code should not land there.
- **`code-issues/private-reach-agent-server-hub.md`**: `hub.py` reads `AgentSession._active`. It matters only if fleet notices touch the hub.

---

### 6. Test conventions

- **Naming**: `tests/test_<area>_<topic>.py`. For example: `test_agent_simulation_tools.py`, `test_agent_simulation_{behaviour,building,weather}_tools.py`, `test_agent_map_tools.py`, `test_bevy_{bridge,wire,capture,ground_truth}.py`, `test_sim_scenario_{manifest,store,e2e}.py`. Acceptance tests use `_e2e`.
- **Shared fakes**: modules named `*_fakes.py` (`sim_fakes`, `agent_tool_fakes`, `agent_server_fakes`, `agent_fakes`, `agent_llm_fakes`, `object_fakes`), imported as `from tests.sim_fakes import …`.
- **Style**:
  - Test names read as plain-English sentences (`test_search_reports_each_hits_licence_verdict`).
  - Bodies carry `# Given … / # When … / # Then …` comments.
  - Builders start with `a_`/`an_` (`a_toolset`, `a_tool_rig`, `a_recorded_run`, `a_session`, `a_chat_rig`, `a_cube`).
  - Drivers and matchers read as English (`the_run_started_by`, `eventually`, `settled`, `finished_call`, `kinds`, `text_of`).
  - `asyncio_mode = "auto"`: plain `async def test_…`.
- **Faking the station**:
  - Real `ScenarioStore` on `tmp_path`, with presets from the real PoC assets (`POC_ASSETS`) and canned HTTP (`RecordingFetch`).
  - A real non-serving `make_demo_server(port=0, with_rtabmap=False, sam_fake=True)` with a tmp history DB, wrapped in a real `DemoWorkspace` (`a_tool_rig`).
  - `EmptyWorkspace` as a stub port.
  - `ScriptedChatModel` for model-driven e2e tests through `build_agent_description` on `HypercornHost` port 0.
- **Faking the sim**:
  - Committed captures under `tests/fixtures/bevy_*`.
  - Byte-exact wire goldens in `tests/fixtures/bevy_sim_wire/`.
  - `FakeBackend`, `FakeRecorder` and `FakeFactory` in `test_bevy_bridge.py`.
  - The real-sidecar e2e skips without the docker image, unless `SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1`.
  - No test fakes a running Bevy instance that receives commands, because no such channel exists.

## Exploration 3: streaming RTAB-Map odometry source — 2026-11-04

**Agent**: parent Grep/Read
**Scope**: does the streaming sidecar use the sim's pose, and what happens after a frame gap?

### Sequence

1. `ls src/surmap/slam` — modules
2. Grep `pose_enu|odometry|odom|def process_frame|class StreamingRtabmapBackend` in `src/surmap/slam/*.py`, `bevy_bridge.py`
3. Read `src/surmap/slam/streaming.py` 55–68

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|---|---|---|---|
| Grep | `pose_enu\|odometry\|odom\|process_frame` | `src/surmap/slam/`, `bevy_bridge.py` | `streaming.py:192` `StreamingRtabmapBackend`, `:348` `process_frame`, `:358` `pose = self._odom.get(frame.frame_id)`; no `pose_enu` in `slam/` |

### Inspected files

#### `src/surmap/slam/streaming.py`

**Why**: odometry source and dropout behaviour.
**Excerpt** (59–62):

```python
# Odom/ResetCountdown: RTAB-Map's default (0) never resets a lost
# odometry, so one dropout ends tracking for the rest of a run (measured
# on NTU VIRAL sbs_01: 719/1200 frames lost; 0/3325 with 1).
DEFAULT_RTABMAP_PARAMS = {"Rtabmap/DetectionRate": "2", "Odom/ResetCountdown": "1"}
```

### Findings

- The streaming backend runs RTAB-Map's **own visual odometry**; the sim's `pose_enu` is not used as odometry (it is ground truth for scoring only).
- A backend kept alive while its drone is inactive sees a frame gap on resume; with `Odom/ResetCountdown: 1` odometry resets and RTAB-Map starts a new sub-map in the same in-memory graph, which joins the earlier one only when a loop closure finds overlap. "Resume/append" is therefore *same process, same graph, possibly disjoint sub-maps until revisited*.

## Exploration 4: delta after `#sim-traffic` (#106, #107, #109) and #115 merged to `main` — 2026-11-04

**Agent**: parent Grep/Read
**Scope**: what changed on `origin/main` (`90dd0ae`) since passes 1–3 read `7efd18b`, in the files this stack touches

### Sequence

1. `git fetch origin`; `git log --oneline -6 origin/main` — confirm `#sim-traffic` 1–3 and #115 merged
2. `git diff --stat 7efd18b origin/main -- examples/bevy-sitl-poc/src src/surmap/simulation src/surmap/agent proto …` — scope of the delta
3. `git show origin/main:examples/bevy-sitl-poc/src/scene_manifest.rs` — `Element`, submodules, validators
4. `git show origin/main:src/surmap/simulation/scenario_manifest.py` — imports, `ELEMENT_KINDS`
5. `git show origin/main:proto/surmap/agent/v1/simulation_tools.proto` — `AddElementRequest` oneof
6. `git show origin/main:examples/bevy-sitl-poc/src/world.rs` — `Builder::element` dispatch
7. `git show origin/main:src/surmap/agent/skills/building-a-simulation-scene/SKILL.md` 1–20 — #115's scene-builder subagent skill
8. `git diff 7efd18b origin/main -- examples/bevy-sitl-poc/src/main.rs examples/bevy-sitl-poc/src/record.rs` — schedule / recorder changes

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|---|---|---|---|
| diff --stat | — | sim, simulation, agent, proto | 55 files, +4887/−764: `vehicle.rs`, `vehicle/scene.rs`, `sea.rs`, `figure_anim.rs`, `actors/{rig,tick,model,figure_def}.rs`, `scene_manifest/{environment,people,water}.rs`, `simulation/{vehicles,water,people}.py`, `agent/subagents.py`, `agent/skills/{building-a-simulation-scene,creating-a-simulation}/SKILL.md` |

### Inspected files

#### `examples/bevy-sitl-poc/src/scene_manifest.rs` (origin/main)

```rust
mod buildings; mod environment; mod nature; mod people; mod water;
pub enum Element { Box(BoxElement), CollapsedBuilding(CollapsedBuilding), Building(Box<Building>),
                   Person(Person), Vegetation(Vegetation), Vehicle(Vehicle) }
// from_json: … validate_weather_fire_vegetation()?; validate_buildings()?; validate_behaviours()?; validate_vehicles()?;
```

#### `proto/surmap/agent/v1/simulation_tools.proto` (origin/main, 338–345)

```proto
oneof element {
  BoxElement box = 2; BuildingElement building = 3; CollapsedBuildingElement collapsed_building = 4;
  PersonElement person = 5; VegetationElement vegetation = 6; VehicleElement vehicle = 7;
}
```

#### `examples/bevy-sitl-poc/src/world.rs` (origin/main, 281–289)

```rust
Element::Vehicle(e) => self.vehicle(e),   // added beside the existing arms
```

#### `src/surmap/agent/skills/building-a-simulation-scene/SKILL.md`

"A subagent's procedure for building a simulation scene with the simulation tools. Pass it as the skill of start_subagent; the main agent does not load it itself." Steps start from `get_scenario` / `create_scenario` with a preset.

#### `main.rs` / `record.rs` diff

`main.rs` adds `mod figure_anim; mod sea; mod vehicle;`, vehicle asset loader, `actors::rig::Rigs`, and vehicle/rig systems chained after `build_world`. `record.rs` imports `VehicleActor` for tracks. The single-`Drone` systems (`fly_scripted`, `follow_drone_rig`, `chase_camera`, `update_status`) are unchanged.

### Findings

- The `#sim-traffic` conflict risk is gone: it is on `main`, and this stack is based on `main`.
- New element pattern to follow: `Vehicle` — enum variant, `validate_vehicles()` called from `from_json`, a `Builder::vehicle` arm, Python `vehicles.py` beside `scenario_manifest.py`, proto oneof field 7. A `drone_nest` takes **oneof field 8** and a `validate_nests()` in a `scene_manifest/fleet.rs` submodule.
- Water now exists (`scene_manifest/water.rs`, `simulation/water.py`): a nest must not sit on water.
- #115's scene-builder subagent follows `skills/building-a-simulation-scene/SKILL.md`; nest placement belongs in that procedure too.
- The single-drone coupling (passes 1–3) is unchanged on `main`.
