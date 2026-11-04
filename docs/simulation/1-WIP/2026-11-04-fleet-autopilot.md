# Changeset: simulated drones on their nests, flown by a kinematic autopilot

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — ordering semantics (a stamped command log replayed deterministically), a pure
autopilot with continuity limits, generalising every single-`Drone` system in the Bevy app with no
headless harness, plus the Python capture loader

PRD: `PRD-2026-11-04-fleet-autopilot.md` · Discovery: `2026-11-04-fleet-autopilot-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-pr-stack` Plan — PRD, changeset, initial discovery · these files (`/plan-pr-stack` pass 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Build and baseline healthy (`uv run mypy`, `uv run pytest -q`, `cargo test --locked`)
  - [ ] Stubs this node owns (`fleet.rs`, `fleet/autopilot.rs`, `fleet/log.rs`, `ActiveDrone`, `FleetDrone`, `--fleet-log`, Python `BevyFrame.drone_id`)
  - [ ] Acceptance tests written and failing for the right reason
  - [ ] Unit/integration tests written and failing
  - [ ] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes (`[G]` on Sonnet only — see Stack Context) ·
  - [ ] `fleet/log.rs`: `FleetCommand`, `Route`, `OnComplete`, `Stamped`, `FleetLog::{push, refused, for_drone, from_jsonl}`; phase checks; golden `tests/fixtures/fleet/commands.json` (every variant) parses
  - [ ] `fleet/autopilot.rs`: fixed-step (`STEP_S = 0.05`) pure `step`; `state_at(home, id, log, t)`; incremental `Autopilot` equal to cold `state_at`; limits; takeoff, legs, detour resume, set_route continuity, recall/land, hover
  - [ ] Runtime: `spawn_fleet` docks one body per `Nests` drone id (`FleetDrone { id }`, kinematic, rotors) and despawns the legacy `Drone` when the scene has nests; `fly_fleet` poses every drone from its `Autopilot` at `SimClock::now()`
  - [ ] `ActiveDrone` resource (first drone by default; `set_active` entries switch it at `at_s`); `follow_drone_rig`, `chase_camera`, `update_status` read "the viewed drone" (active fleet drone, else legacy `Drone`)
  - [ ] Recorder: `pose_enu` from the viewed drone's pure pose at `t`; `frames.jsonl` `drone_id` when fleet; `--fleet-log <path>` in `RunMode`
  - [ ] UI: status line names the active drone, phase and leg; fleet list (id · phase)
  - [ ] Python `bevy_capture.py`: `BevyFrame.drone_id: str | None` read from `frames.jsonl`
  - [ ] Gates green; `cargo test --locked`; `cargo check --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (tests + native stills of `earthquake-fleet` replaying `survey-sortie.fleet.jsonl`)
  - [ ] `docs/simulation/bevy-simulation.md` — *The fleet and its autopilot* (commands, limits, phases, fleet log, `--fleet-log`, active drone); the `survey-loop` text names when it applies
  - [ ] `docs/simulation/changelog/2026-11-04-fleet-autopilot.md`
  - [ ] `src/surmap/docs/todo/` — new TODO: obstacle avoidance and drone-to-drone separation
  - [ ] Validate tests (`/validate-tests`)
  - [ ] (optional) Clean-code pass (`/analyze-clean-code`) — run if `main.rs` or `fleet/autopilot.rs` passes 500 lines
  - [ ] Lint (`ruff --no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-04-fleet-autopilot-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Stack Context

**Stack**: drone nests and an agent-tasked simulated fleet · slug **`#drone-fleet`** — this PR is
**2 of 5** · `#pending`
**Branch**: `pr-2-drone-fleet` · **Base**: `pr-1-drone-fleet`
**Successor**: `pr-3-drone-fleet`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = `/plan-red` Steps 7–9 (stubs, failing acceptance + unit tests)
**Workflow override**: `[G]` (the Green row) runs on **Sonnet only**, instead of the
`/yolo-pr-stack` rubric's Haiku column. Effort comes from this node's complexity: 1–2 low,
3 medium, 4–5 high. A `[G]` retry stays on Sonnet, one effort step up, and never goes to Opus.
`[W]`/`[F]` keep the default rubric. Approved by the developer, 2026-11-04, for the whole
`#drone-fleet` stack. See `## Decisions & Trade-offs`.

Why the boundary falls here: everything that moves a simulated drone lives inside the renderer
and is driven by a file. The fleet log is the seam. This node owns its format and the autopilot
that replays it; n3 only appends to the log live. With no nests the app is unchanged, so it
merges alone.

### Owned API surface

- Rust `fleet` module:
  - `fleet/log.rs`:
    - `FleetCommand` (serde `tag = "type"`, snake_case: `launch {drone, route}`,
      `set_route {drone, route}`, `detour {drone, waypoints}`, `recall {drone}`,
      `set_active {drone}`)
    - `Route { waypoints: Vec<[f32; 3]>, speed_m_s = 5.0, on_complete = Return }`,
      `OnComplete { Return, Hover }`
    - `Stamped { seq: u64, at_s: f32, command }`
    - `Refusal { seq, at_s, reason }`
    - `FleetLog { push(at_s, command) -> Result<u64, Refusal>, entries(), refused(), for_drone(id),
      from_jsonl(str) }`
  - `fleet/autopilot.rs`:
    - `Home { pad_enu, yaw_deg }`
    - `Phase { Docked, Climbing, Cruising, Detouring, Hovering, Returning, Landing }`
    - `DroneState { position_enu, velocity_enu, yaw_deg, phase, target, legs_left }`
    - `step(state, plan, dt)`, `state_at(home, id, log, t_s)`, `Autopilot` (incremental)
    - limits `MAX_SPEED_M_S = 8.0`, `MIN_SPEED_M_S = 0.5`, `MAX_ACCEL_M_S2 = 2.5`,
      `MAX_CLIMB_M_S = 2.0`, `MAX_YAW_RATE_DEG_S = 60.0`, `REACH_M = 1.0`,
      `MIN_UP_M = 5.0`, `MAX_UP_M = 60.0`
  - `fleet.rs`: `FleetDrone { id }`, `ActiveDrone(Option<String>)`, the `Fleet` resource (log and
    autopilots), the systems `spawn_fleet` and `fly_fleet`, and `viewed_pose(t)`.
- `RunMode.fleet_log` / `--fleet-log`; `frames.jsonl` `drone_id`.
- Fixtures: `tests/fixtures/fleet/commands.json` (one of each command — **the cross-language
  command contract**; n3's Python codec reads it) and `tests/fixtures/fleet/survey-sortie.fleet.jsonl`.
- Python: `bevy_capture.BevyFrame.drone_id`.

### Green wave

**Wave:** 2 of 3
**Node:** n2
**Concurrent with:** n3
**Blocks:** n5 (streams the active drone's pairs — needs `ActiveDrone` to really switch and the
eyes to follow it)

Real dependency edges, as opposed to the branch line:

    n1 → n2, n3      n2 → n5      n3 → n4      n4 → n5 (compile only: n5 adds an rpc to n4's service)

### Greenable independently?

**no — blocked by n1** (`pr-1-drone-fleet`). The spawn tests and the fixture tests parse manifests
with `drone_nest` elements, so they need n1's `validate_nests` and `Nests` to really work. The
pure autopilot and log tests take a `Home` value and are green-able against n1's stubs. A spawn or
fixture test that is still red because of `TODO(pr-1)` is blocked on n1, not a failure.

### Trunk-merge safety

**When this PR merges alone:** additive. Without nests, `spawn_fleet` spawns nothing and the
legacy `Drone`, `fly_scripted` and `record_frames` take today's paths. The existing
`survey-loop` record tests and `tests/fixtures/bevy_*` captures are unchanged. `drone_id` is an
optional key, and the Python loader treats it as absent on old captures. `cargo test`,
`trunk build`, `uv run pytest -q` keep working. **Local dev data:** none. **Production data:**
none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `scene_manifest::DroneNest`, `Element::DroneNest`, `DroneNest::drone_ids()` | n1 | stub, `TODO(pr-1)` | reads them; does not implement them |
| `scene_manifest/fleet.rs` `validate_nests` | n1 | stub, `TODO(pr-1)` | its fixture-parse tests wait on it |
| `world::Nests` resource (`Nest { id, pad_enu, yaw_deg, drone_ids }`), `NestPad` | n1 | stub, `TODO(pr-1)` | `spawn_fleet` reads `Nests`; pure tests build `Home` directly |
| preset `earthquake-fleet` | n1 | stub | the native stills at wrap use a manifest written from it |

**Greenable independently?** no — needs n1 green first (spawn and fixture tests).

## Background

The developer (2026-11-04) asked that the agent can "activate a drone, plan its trip route (on
auto-pilot), adjust the route mid-course, do detours etc. There can be multiple drones in-flight,
but only input of 1 drone would be visible on screen". The scope decision of the same day
(n1, `docs/architecture.md` §1) allows tasking the simulation's own drones only. This node is
the drones and their autopilot inside the renderer; who issues the commands is n3/n4.

## Technical Changes

### State A (Current)

- **One hard-coded drone.** `main.rs::setup_drone` spawns a single `Drone` (a unit marker). It is
  `KinematicPositionBased` for the scripted flight.
- **Every system assumes one drone.** `fly_scripted` (`shots.rs:139-155`), `follow_drone_rig`,
  `chase_camera`, `read_controls` and `ui::update_status` use `single()` / `single_mut()`.
  `Flight`, `StereoFeeds`, `CameraProfile` and `Recorder` are global.
- **The eyes** are top-level cameras, re-posed every frame from the drone body plus the profile's
  mount (`main.rs:347-360`).
- **The flight** is `SurveyLoop::disaster_block().pose_at(t)`, a pure function of time
  (`flight.rs`). The recorder recomputes `pose_enu` from it (`record.rs:250-251`).
- **Time.** `SimClock::now()` is `SimTime` (pinned for stills and lockstep recording) or elapsed
  time. Behaviours tick at a fixed 10 Hz.
- **No headless Bevy App tests.** All Rust tests are pure functions (`flight.rs` is the model).
- **After n1:** nests parse, render as pads, and fill `Nests` with drone ids. No drone sits on
  them.

### State B (Target)

#### The fleet log

One JSON object per line, in `at_s` order (ties by `seq`). The same shape is what n3 sends live:

```json
{"seq": 1, "at_s": 2.0, "command": {"type": "launch", "drone": "nest-sw-d1",
  "route": {"waypoints": [[-10, 20, 12], [10, 60, 15]], "speed_m_s": 5, "on_complete": "return"}}}
{"seq": 2, "at_s": 9.5, "command": {"type": "detour", "drone": "nest-sw-d1", "waypoints": [[0, 35, 18]]}}
{"seq": 3, "at_s": 12.0, "command": {"type": "set_active", "drone": "nest-sw-d1"}}
```

`FleetLog::push(at_s, command)` checks the command against the drone's phase at `at_s` (replayed
from the log so far). It returns the assigned `seq`, or a `Refusal` with one of these reasons:

- unknown drone
- `launch` when not `Docked`
- `set_route` / `detour` when `Docked` or `Landing`
- `recall` when `Docked`
- empty waypoints
- speed outside 0.5–8
- a waypoint `up` outside 5–60

Refusals are kept (`refused()`), never applied. `from_jsonl` keeps file `seq`s and refuses
out-of-order `at_s`.

#### The autopilot

- **Fixed step.** `STEP_S = 0.05` from `t = 0`, so the result is independent of frame rate. A
  command takes effect at the first step at or after its `at_s`.
- **Pure.** `state_at(home, id, log, t)` is pure. The runtime `Autopilot` advances incrementally
  and must equal `state_at` at every `t` (a test).

| Phase | Motion |
|---|---|
| `Docked` | on the pad, at `pad_enu`, facing `yaw_deg`. The rig centre is the pad plus the body offset |
| `Climbing` | vertical at ≤ 2 m/s to the first target's `up` (at least 5 m above the pad), then `Cruising` |
| `Cruising` | toward the current target. Horizontal speed ramps at ≤ 2.5 m/s² up to the route speed. Vertical speed ≤ 2 m/s. Heading turns toward the velocity at ≤ 60°/s. A target within 1 m is reached and the next one becomes current |
| `Detouring` | as `Cruising`, over the detour's waypoints. After the last one, the target that was current when the detour arrived resumes |
| `Hovering` | holds position, decelerating to 0 within the acceleration limit (`on_complete: hover`) |
| `Returning` | cruises to the point above the pad at the current altitude (`recall`, or `on_complete: return`) |
| `Landing` | vertical descent at ≤ 1 m/s to the pad, then `Docked` |

`set_route` replaces the remaining targets. It never resets position or velocity, so the path
stays continuous (each step moves at most `MAX_SPEED_M_S · STEP_S + ε`).

#### Runtime

- **Spawning.** `spawn_fleet` runs after `build_world`. For each `Nests` drone id it spawns a body
  (the legacy body's frame and four rotors, factored into `drone_body()`), tagged
  `FleetDrone { id }` and kinematic. When the scene has nests, the legacy `Drone` is despawned.
- **Flying.** `fly_fleet` sets every fleet drone's transform from its `Autopilot` at
  `SimClock::now()`. Rotors spin when the drone is not `Docked`.
- **The active drone.** `ActiveDrone` starts as the first drone id. `set_active` entries switch it
  at their `at_s`. "The viewed drone" is the active fleet drone, else the legacy `Drone`.
  `follow_drone_rig`, `chase_camera` and `update_status` follow the viewed drone. Keyboard flight
  applies only to the legacy drone.
- **Recording.** `record_frames` takes `pose_enu` from `viewed_pose(t)`, which is pure: the fleet
  autopilot's pose of the active drone at `t`, else `SurveyLoop`. With a fleet it writes
  `"drone_id"` on each frame line. `--fleet-log <path>` loads a log for stills and recordings.
  Without nests, stills and recordings force `survey-loop` as today.
- **Python.** `load_bevy_capture` accepts an optional `drone_id` per frame
  (`BevyFrame.drone_id: str | None`). Old captures load unchanged.

### Delta (What's Changing)

#### examples/bevy-sitl-poc

- New: `fleet.rs`, `fleet/log.rs`, `fleet/autopilot.rs`, `fleet/tests.rs`, `fleet/autopilot/tests.rs`.
- `main.rs`: register the fleet systems; the viewed-drone queries; `drone_body()`.
- `shots.rs`: `RunMode.fleet_log`, the `--fleet-log` flag, and fleet-aware forcing of
  `survey-loop`.
- `record.rs`: `viewed_pose`, `drone_id`.
- `ui.rs`: status and fleet list.

#### surmap

- `simulation/bevy_capture.py` (`drone_id`); `tests/test_bevy_capture.py` (case).
- New fixtures: `tests/fixtures/fleet/commands.json`, `tests/fixtures/fleet/survey-sortie.fleet.jsonl`.

## Verification

**Method:** V1 fail→pass. These are pure Rust tests of the log and autopilot, the acceptance
criteria as tests, and the recorder pose source. A Python test covers `drone_id` loading.
**Command:** `cd examples/bevy-sitl-poc && cargo test --locked fleet` and
`uv run pytest -q tests/test_bevy_capture.py`
**Before:** the new tests fail on the `fleet` stubs (`todo!()`). The Python case fails on the
missing `drone_id`.
**After:** all pass. The existing `flight.rs`, `record.rs` and capture tests still pass, which
shows the no-nests path is unchanged.

What blocks a higher-tier check: there is no headless Bevy harness (discovery Exploration 1, Q6),
so the systems are tested through their pure functions (`viewed_pose`, `state_at`, `push`).
Supporting evidence (not a rung): native stills at `--at 20` and `--at 40` of `earthquake-fleet`
replaying `survey-sortie.fleet.jsonl` (two drones airborne, the feed on the active one), reviewed
at wrap.

## Acceptance Tests

- `a_launched_drone_climbs_off_its_pad_then_reaches_each_waypoint_in_order`
- `no_drone_ever_exceeds_the_speed_climb_or_turn_limits` (sampled over the sortie)
- `a_new_route_mid_flight_turns_from_where_the_drone_is_without_a_jump`
- `a_detour_visits_its_waypoints_then_resumes_the_waypoint_that_was_next`
- `a_recalled_drone_lands_back_on_its_own_pad_and_docks`
- `two_drones_fly_at_once_without_changing_each_others_path`
- `the_same_log_and_moment_give_the_same_pose` / `the_incremental_autopilot_matches_the_replayed_one`
- `after_set_active_recorded_frames_carry_the_new_drones_id_and_pose` (via `viewed_pose` and `frame_line`)
- `a_refused_command_leaves_the_flight_unchanged_and_names_the_reason` (one per refusal reason)
- `a_scene_without_nests_records_the_survey_loop_as_before`
- `every_command_in_the_shared_fixture_parses` (`tests/fixtures/fleet/commands.json`)
- Python: `test_a_fleet_capture_names_the_drone_on_every_frame`, `test_an_old_capture_loads_without_drone_ids`

## Prerequisites

| Item | Verdict |
|---|---|
| `todo/2026-11-03-bevy-loop-closure-acceptance.md` | ℹ unrelated to the fleet; the `survey-loop` stays untouched, so its acceptance is unaffected |
| `todo/2026-11-03-bevy-visual-checkpoints-v3-v5.md` | — unrelated |
| everything else | — unrelated |

`examples/bevy-sitl-poc` has no `docs/code-issues/` directory, so it has never been analyzed.
`main.rs` is 417 lines on `main`. If this node pushes it past 500, `/pr-wrap`'s clean-code pass
decides the split (planned as optional under Wrap).

## Decisions & Trade-offs

- **Simulation-time-stamped log, pure autopilot.** Recordings and stills must replay, and there is
  no headless harness, so the only testable shape is a pure function. Re-simulating from `t = 0` is
  O(t / 0.05); `Autopilot` caches state for the live app, and `state_at` is the oracle in tests.
- **Kinematic, not physical.** Drones are `KinematicPositionBased`, like the scripted loop. There
  is no rapier dynamics, wind or battery, so flight is deterministic and cheap with several drones.
- **No obstacle avoidance or separation.** The route is flown as given, so the agent must plan
  around buildings. This is filed as a TODO at wrap. Avoidance would make the autopilot a path
  planner, which is far more than the stack needs.
- **The sim refuses invalid commands as well as the station (n3).** A log file from disk, or a race
  with a phase change, must never leave a drone half-commanded.
- **The legacy drone is despawned when nests exist.** Keeping two control schemes alive in one scene
  would make "the viewed drone" ambiguous. Scenes without nests keep keyboard flight.
- **`[G]` on Sonnet only** (developer, 2026-11-04, whole stack): Sonnet · high instead of the
  rubric's Haiku · xhigh for complexity 4.
