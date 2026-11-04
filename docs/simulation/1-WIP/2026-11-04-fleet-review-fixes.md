# Changeset: #drone-fleet review fixes

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Bug Fix
**Behaviour**: changes
**Complexity**: 4 — two languages (Rust wasm stream, Python bridge/controller/agent), concurrency
(moving bridge work off the shared event loop, ack timing), a proto field addition, ten
independent fixes each with its own reproduction

Discovery: `2026-11-04-fleet-review-fixes-initial-discovery.md` · PRD: none — bug fixes. The one
user-visible addition, `list_drones` reporting `sim_t_s`, restores a field the n4 PRD already
planned.

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · these files (review of `bd30dc1..53858eb`, findings verified)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation — None: bug fixes; F10 restores a field n4's PRD planned
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — reproduction tests, committed ·
  - [ ] Build and baseline healthy (`uv run mypy`, `uv run pytest -q`, `cargo test --locked`)
  - [ ] One reproduction per finding F1–F10, each failing because of the defect (see `## Reproductions`)
  - [ ] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — fix until every reproduction passes ·
  - [ ] F1 bridge SAM: the agent's configured SAM (station detector, else the fake under `--sam-fake`), one detector per drone session, nothing retained per frame
  - [ ] F2 a streamed pair's `drone_id` is the drone whose eyes were read back (captured with `pending_pose` / `pending_t_ns`)
  - [ ] F3 bridge `handle` / `close` run off the event loop (`asyncio.to_thread`), so the agent loop keeps serving while a backend starts or closes
  - [ ] F4 an applied command's expected phase is kept until telemetry stamped at or after the step the page applies it at
  - [ ] F5 one drone's backend failure marks that session errored and reports it in its status; the connection and the other drones keep running
  - [ ] F6 a fleet link whose `hello.scenario` differs from `?scenario=` is closed with 4400 and never attached
  - [ ] F7 `stream_bridge` runs after `fleet::fly_fleet` and `follow_drone_rig`
  - [ ] F8 an unlinked controller validates against the scenario's latest nests
  - [ ] F9 `tests/hang_dump.py` skips a dead weak proxy instead of raising `ReferenceError`
  - [ ] F10 `ListDronesResponse.sim_t_s` (the linked page's telemetry time; 0 when unlinked); proto + generated code; `docs/agent.md` field table
  - [ ] Gates green; `cargo test --locked`; `cargo check --locked --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/simulation/bevy-simulation.md` — *Live stream* / *The fleet link*: the bridge's SAM, off-loop work, per-drone failure isolation, the scenario check
  - [ ] `docs/simulation/changelog/2026-11-04-fleet-review-fixes.md`
  - [ ] `src/surmap/docs/todo/2026-11-04-fleet-browser-verification.md` — add a step: after a `set_active` switch mid-stream, the first pair after the switch is labelled with the new drone
  - [ ] Validate tests (`/validate-tests`)
  - [ ] Lint (`ruff --no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-04-fleet-review-fixes-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Background

The `#drone-fleet` stack (drone nests, kinematic autopilot, fleet link, FleetTools, per-drone
perception; #116–#121) was implemented and merged on 2026-11-04. The developer then asked to
"review its work and let's add a PR with improvements/fixes". A high-effort review of
`bd30dc1..53858eb` produced 10 findings. All were verified against the code (discovery,
Exploration 2). This PR fixes the 8 behaviour defects plus 2 from the stage reports. The 2
behaviour-preserving findings go to a separate Refactor PR, with the stack's three oversized-file
code issues: a refactor's baseline must not move under a behaviour change.

## Technical Changes

### State A (Current)

| # | Today |
|---|---|
| F1 | `start_bevy_bridge` gives every drone's `SamSegmentationSink` the one shared `InMemorySamDetector()` test fake. It returns zero detections and appends every frame to an unbounded list (memory grows about 3 MB/s per streaming drone) |
| F2 | `stream_bridge` reads `ActiveDrone` when the readback lands, while pose and `t_ns` were taken at the request |
| F3 | `serve_bevy_bridge`'s handler calls `session.handle(message)` / `session.close()` synchronously on the agent server's loop |
| F4 | `FleetController` drops an expectation at telemetry `sim_t_s >= at_s`, but the page applies at `due_step(at_s)`, up to one 0.05 s step later |
| F5 | `FleetPerception.handle` lets a backend exception escape and end the connection |
| F6 | `FleetRegistry.link` attaches a page whose `hello.scenario` names another scenario |
| F7 | `stream_bridge` has no `.after(fleet::fly_fleet)` / `.after(follow_drone_rig)` |
| F8 | `FleetRegistry.controller` freezes the nests at first use |
| F9 | `tests/hang_dump.py::_pending_tasks` raises `ReferenceError` on a dead `weakref.proxy` in `gc.get_objects()` |
| F10 | `ListDronesResponse` has no `sim_t_s`; n4's PRD planned it |

### State B (Target)

| # | After |
|---|---|
| F1 | The bridge's segmentation uses the agent's configured SAM: the station's detector when `--station` is set, else the fake centred-box SAM under `--sam-fake`, adapted to `SamDetector` if needed. Each drone session gets its own detector instance. Nothing in the segmentation path keeps frames after `detect` returns. `InMemorySamDetector` is used only by tests |
| F2 | `BridgeStream` records the active drone id at readback request, next to `pending_pose` / `pending_t_ns`. A pure helper the tests can drive (e.g. `PendingPair` captured at request) carries all three |
| F3 | The handler runs `session.handle` and `session.close` through `asyncio.to_thread`. Messages of one connection are still processed in order |
| F4 | An expectation stands until telemetry `sim_t_s >= applied_at(at_s)`, where `applied_at` mirrors the renderer's `due_step` (`ceil(at_s / 0.05 − slack) · 0.05`). The 0.05 s step and the slack are shared constants with a comment pointing at `autopilot.rs` |
| F5 | `DroneSession.process` catches the backend's exception. It marks the session `errored` (counts frozen, backend closed once) and returns a status with `drone_id` and `error`. Later pairs for that drone get the same error status without touching the backend. Other drones and the socket keep running. `drone_map_status` reports the error per drone |
| F6 | `link` closes with `CLOSE_PROTOCOL_ERROR` (4400) when `hello.scenario` is present and differs from the linked scenario id. No session is recorded |
| F7 | `app.add_systems(Update, stream_bridge.after(fleet::fly_fleet).after(follow_drone_rig))`. `follow_drone_rig` becomes reachable from the plugin, or the ordering goes through a shared `SystemSet` |
| F8 | While unlinked, a controller reads the scenario's latest manifest nests on each validation. Linked, the page's `hello` drones stay authoritative as today. On detach, the retained telemetry no longer drives phase checks: commands answer UNAVAILABLE first |
| F9 | `_is_event_loop(obj)` returns False on `ReferenceError` |
| F10 | `optional double sim_t_s` on `ListDronesResponse`: the last telemetry's `sim_t_s` while linked, unset when unlinked. Exposed by a `FleetController.telemetry_time()` accessor |

### Delta (What's Changing)

- **Python:**
  - `src/surmap/agent/server/app.py` (F1)
  - `src/surmap/simulation/bevy_bridge.py` (F3)
  - `src/surmap/simulation/fleet/controller.py` (F4, F6, F8, F10)
  - `src/surmap/simulation/fleet/perception.py` (F5)
  - `src/surmap/agent/tools/fleet_handlers.py` (F5 status, F10)
  - `proto/surmap/agent/v1/fleet_tools.proto` + generated code (F10)
  - `tests/hang_dump.py` (F9)
- **Rust:** `examples/bevy-sitl-poc/src/fleet/bridge_wasm.rs` and `fleet/stream.rs` (F2, F7).
- **Tests:**
  - `tests/test_fleet_perception.py`, `tests/test_fleet_perception_e2e.py` (F1, F3, F5)
  - `tests/test_sim_fleet_controller.py`, `tests/test_sim_fleet_registry.py` (F4, F6, F8)
  - `tests/test_agent_fleet_tools.py` (F5, F10)
  - `tests/test_agent_server_app.py` (F1)
  - `tests/test_hang_dump.py` (F9)
  - Rust `fleet/stream.rs` tests (F2)

## Reproductions

Each is a test that fails on `main` because of the defect, not a missing symbol. A new symbol is
added only where a pure seam is needed to reach the defect, and it is named in the Red commit.

| # | Reproduction (V1 fail→pass) | Fails today because |
|---|---|---|
| F1 | `test_the_bridge_segments_with_the_agents_configured_sam` (with `--sam-fake`, the bridge's sinks run the centred-box SAM and report detections > 0), and `test_a_streaming_drone_keeps_no_frames_after_segmenting_them` (after N pairs, no detector holds N frames) | detections are 0, and `InMemorySamDetector.frames` grows to N |
| F2 | Rust: `a_switch_while_the_eyes_are_read_back_keeps_the_requesting_drones_id` (capture at request with drone A, set active B, complete: the header says A) | the id is taken at completion, so it says B |
| F3 | `test_a_slow_backend_start_does_not_stall_the_event_loop` (a backend factory blocking 0.5 s; a concurrent `asyncio.sleep(0.01)` ticker keeps ticking during the first pair) | the ticker is starved for the whole 0.5 s |
| F4 | `test_telemetry_from_the_frame_a_launch_lands_in_keeps_the_drone_climbing` (applied `at_s=1.02`, telemetry `sim_t_s=1.02 phase=docked`; then `recall` passes the station check) | the expectation is dropped and the recall is refused `already_docked` |
| F5 | `test_one_drones_backend_failure_leaves_the_other_drones_streaming` (backend B raises on its 3rd frame; A keeps processing; B's status carries the error; the socket stays open) | the exception closes every session |
| F6 | `test_a_page_whose_hello_names_another_scenario_is_refused` (link `?scenario=A` with `hello.scenario=B` closes 4400, and A stays unlinked) | it attaches, and A accepts B's drones |
| F7 | Rust: covered by F2's seam test plus a schedule-order check if one is expressible (e.g. the plugin registers `stream_bridge` in a set ordered after the fleet set, asserted on the `App`'s schedule graph). Otherwise V3: `cargo check --target wasm32-unknown-unknown` with the ordering compiled in, plus the browser TODO step | no ordering exists |
| F8 | `test_a_nest_added_after_the_first_call_has_drones_the_controller_knows` (call `list_drones`, add a nest, `launch_drone` on the new drone while unlinked answers UNAVAILABLE, not NOT_FOUND) | NOT_FOUND, from the frozen nests |
| F9 | `test_a_dead_weak_proxy_in_memory_does_not_cut_the_report_short` (prepared patch) | `ReferenceError` |
| F10 | `test_list_drones_reports_the_pages_simulation_time` (telemetry `sim_t_s=41.5`; `list_drones.sim_t_s == 41.5`; unset when unlinked) | no such field |

## Verification

**Method:** V1 fail→pass — the ten reproductions above, red on `main` and green after. F7's
schedule order is V1 if the `App` graph assertion is expressible, else V3 (the wasm build with the
ordering), and the browser-verification TODO gains the post-switch labelling step.
**Command:** `uv run pytest -q tests/test_fleet_perception.py tests/test_fleet_perception_e2e.py tests/test_sim_fleet_controller.py tests/test_sim_fleet_registry.py tests/test_agent_fleet_tools.py tests/test_agent_server_app.py tests/test_hang_dump.py`
and `cd examples/bevy-sitl-poc && cargo test --locked stream`
**Before:** each reproduction fails with the cause in the table (recorded in the Red commit).
**After:** all pass. The full suites stay green.

## Prerequisites

| Item | Verdict |
|---|---|
| `todo/2026-11-04-fleet-browser-verification.md` | ⚠ during — gains the F2/F7 post-switch check (Wrap TODO); stays open for the developer's post-merge run |
| `todo/2026-11-03-agent-cli-sam-flags.md` | ℹ F1 follows the agent's existing SAM choice (station or `--sam-fake`); it does not lift that todo's constraint |
| `code-issues/oversized-file-world.md`, `…-scenario-manifest.md`, `…-simulation-tools-proto.md` | — out of scope: the Refactor follow-up PR |
| `todo/2026-11-04-fleet-obstacle-avoidance.md`, `…-fleet-routes-on-chat-map.md` | — unrelated |

## Decisions & Trade-offs

- **The 2 behaviour-preserving findings are not here.** The quadratic replay (R1) and the duplicated
  frame path (R2) go to a Refactor PR with the three oversized-file code issues, so its baseline
  guards a pure move. Mixing them in would make the reproductions and the refactor baseline
  disagree about what changed.
- **F1 uses the agent's own SAM choice.** It does not add a bridge-specific flag. The bridge serves
  the same station.
- **F4 mirrors the renderer's step rule in Python** rather than changing the wire to carry the
  applied step. That keeps `fleet/v1` unchanged, and a comment ties the constant to `autopilot.rs`.
- **F10 is included** although it adds a field: it restores n4's planned contract, and it is one
  `optional` field with no behaviour change for existing callers.
