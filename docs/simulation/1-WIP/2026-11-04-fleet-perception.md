# Changeset: only the active drone is mapped and segmented, each drone into its own map

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — wire contract change (`pair.drone_id`, both languages, goldens), a per-drone
session router with live backends kept idle (concurrency, resource cap, close ordering), a CI
real-sidecar job edit, a new rpc on n4's service, an agent CLI flag, and a wasm-only streaming
client with GPU readback

PRD: `PRD-2026-11-04-fleet-perception.md` · Discovery: `2026-11-04-fleet-perception-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-pr-stack` Plan — PRD, changeset, initial discovery · these files (`/plan-pr-stack` pass 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Build and baseline healthy (`uv run mypy`, `uv run pytest -q`, `cargo test --locked`)
  - [ ] Stubs this node owns (`fleet/perception.py`, `PairHeader.drone_id`, `BevyPair.drone_id`, `DroneMapStatus` rpc, Rust `fleet/stream.rs`, `fleet/bridge_wasm.rs`)
  - [ ] Acceptance tests written and failing for the right reason
  - [ ] Unit/integration tests written and failing
  - [ ] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes (`[G]` on Sonnet only — see Stack Context) ·
  - [ ] Wire: optional `drone_id` on `pair` (Rust `PairHeader`, `encode_pair`; Python `decode_bevy_message`, `BevyPair`); optional `scenario` on `hello`; `status` gains `drone_id`; `hello.bin`/`pair.bin` byte-identical, new golden `pair-drone.bin`
  - [ ] Python `fleet/perception.py`: `DroneSession` (backend, `SegmentationSink`, counts, optional per-drone `CaptureRecorder`), `FleetPerception` router (get-or-create per drone, `MAX_DRONE_SESSIONS = 4`, idle keeps backend, close finishes all), `PerceptionRegistry` keyed by scenario
  - [ ] `SamSegmentationSink` over `surmap.survey.sam.SamDetector` (left frame → detections, counted); `InMemorySamDetector` in tests
  - [ ] `serve_bevy_bridge` takes the router; `python -m surmap.agent --bevy-bridge-port` starts it with the streaming RTAB-Map factory and the configured SAM detector
  - [ ] `FleetTools.DroneMapStatus` (SYNC · 10 s · FAIL) in n4's proto + regenerated code; handler beside n4's; registered with them
  - [ ] Rust `fleet/stream.rs` (pure): `StreamPacer` (send at `rate_hz` of sim time, drop when `buffered_bytes > cap`), `pair_for(active, …)`; `fleet/bridge_wasm.rs`: `?bridge=ws://…` → binary `WebSocket`, `hello` at scene ready, eye `Readback` → `encode_pair` with the active drone id; status replies shown on the page (`ui.rs`)
  - [ ] Real-sidecar e2e `tests/test_fleet_perception_rtabmap_e2e.py` added to the `rtabmap-e2e` CI step
  - [ ] Gates green; `cargo test --locked`; `cargo check --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (V1 suites incl. the real-sidecar e2e; V3 wasm check; V4 Chrome procedure with the status overlay and `drone_map_status` output)
  - [ ] `docs/simulation/bevy-simulation.md` — *Live stream* (the "not yet built" text at ~627–630 replaced): `?bridge=`, per-drone sessions, the cap, resume semantics
  - [ ] `docs/agent.md` — `drone_map_status` row and fields; `--bevy-bridge-port`
  - [ ] `docs/architecture.md` §2.3 — the active drone's feed is the session the pipeline consumes, one map per drone
  - [ ] `src/surmap/docs/todo/2026-11-03-bevy-live-websocket-stream.md` — resolved by this PR (record what was delivered)
  - [ ] `docs/simulation/changelog/2026-11-04-fleet-perception.md`
  - [ ] Validate tests (`/validate-tests`)
  - [ ] Production readiness validated (`/validate-prod-ready`) — long-lived backends, resource cap, close paths
  - [ ] Lint (`ruff --no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-04-fleet-perception-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Stack Context

**Stack**: drone nests and an agent-tasked simulated fleet · slug **`#drone-fleet`** — this PR is
**5 of 5** · `#pending`
**Branch**: `pr-5-drone-fleet` · **Base**: `pr-4-drone-fleet`
**Successor**: none — top of stack
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = `/plan-red` Steps 7–9 (stubs, failing acceptance + unit tests)
**Workflow override**: `[G]` (the Green row) runs on **Sonnet only**, instead of the
`/yolo-pr-stack` rubric's Haiku column. Effort comes from this node's complexity: 1–2 low,
3 medium, 4–5 high. A `[G]` retry stays on Sonnet, one effort step up, and never goes to Opus.
`[W]`/`[F]` keep the default rubric. Approved by the developer, 2026-11-04, for the whole
`#drone-fleet` stack. See `## Decisions & Trade-offs`.

Why the boundary falls here: perception is the consumer side, from the stereo bridge to RTAB-Map
and SAM. It shares no code with the command path (n3/n4) except the one status rpc it adds to
n4's service.

### Owned API surface

- Wire:
  - `wire::PairHeader.drone_id: Option<String>`, `encode_pair(…, drone_id)`;
  - Python `bevy_wire.BevyPair.drone_id`, `BevyHello.scenario`;
  - `encode_status(…, drone_id)`;
  - golden `tests/fixtures/bevy_sim_wire/pair-drone.bin`.
- Python `surmap.simulation.fleet.perception`:
  - `DroneSession`, `DroneCounts`, `FleetPerception` (`handle(message) -> BridgeStatus`,
    `counts()`, `processing()`, `close()`);
  - `MAX_DRONE_SESSIONS`, `SegmentationSink`, `SamSegmentationSink`, `PerceptionRegistry`.
- `bevy_bridge.serve_bevy_bridge` accepting the router; `python -m surmap.agent --bevy-bridge-port`.
- Proto: `FleetTools.DroneMapStatus` with `DroneMapStatusRequest/Response` and `DroneMapCounts`;
  its handler `drone_map_status`.
- Rust: `fleet/stream.rs` (`StreamPacer`, `pair_for`), `fleet/bridge_wasm.rs` (`BridgeStreamPlugin`,
  `?bridge=` parse), the page status line.
- CI: `tests/test_fleet_perception_rtabmap_e2e.py` in the `rtabmap-e2e` job.

### Green wave

**Wave:** 3 of 3
**Node:** n5
**Concurrent with:** n4
**Blocks:** nothing

Real dependency edges, as opposed to the branch line:

    n1 → n2, n3      n2 → n5      n3 → n4      n4 → n5 (compile only: n5 adds an rpc to n4's service)

### Greenable independently?

**no — blocked by n2** (`pr-2-drone-fleet`). The wasm stream labels each pair with n2's
`ActiveDrone` and reads the eyes n2 makes follow it. The page-level tests and the V4 run need the
drone switch to really happen.

Its rpc also compiles against **n4**'s `fleet_tools.proto` and registers beside n4's handlers.
`test_drone_map_status_reports_every_drone` goes through the registered `FleetTools` service, so
it waits for n4's registration to be real.

The Python router, wire and real-sidecar tests feed pairs with drone ids directly, so they do not
wait on n2.

### Trunk-merge safety

**When this PR merges alone:** additive.

- `drone_id` is optional on the wire: the old goldens stay byte-identical, and a pair without it
  is the default drone.
- The bridge starts only with `--bevy-bridge-port`, and the page streams only with `?bridge=`.
- The CI `rtabmap-e2e` step runs one more test file against the image it already builds.

`uv run pytest -q`, `cargo test`, `trunk build` and the agent server's start keep working.
**Local dev data:** none. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `ActiveDrone`, `FleetDrone`, eyes following the viewed drone, `viewed_pose` | n2 | stub, `TODO(pr-2)` | the wasm stream reads `ActiveDrone` for `drone_id` |
| `BevyFrame.drone_id`, `frames.jsonl` `drone_id` | n2 | stub | the real-sidecar e2e splits a capture into two drones' blocks by it (or by frame range on the committed capture) |
| `?fleet=` page-parameter parsing pattern, `web-sys` `WebSocket` features | n3 | real once n3 greens | reuses them for `?bridge=` |
| `FleetRegistry` / `SimulationRig.fleet` | n3 | stub | the status tool resolves the scenario's drones through it |
| `fleet_tools.proto` `FleetTools`, `fleet_handlers.fleet_tool_handlers`, `services.fleet_module`, registration | n4 | stub, `TODO(pr-4)` | adds one rpc and one handler beside them; does not change theirs |

**Greenable independently?** no — needs n2 green (active drone), and n4's registration for the
status tool's e2e.

## Background

The developer (2026-11-04): "There can be multiple drones in-flight, but only input of 1 drone
would be visible on screen (the agent would decide which one) and that drone's RTAB-map and
segmentation would be in process."

Decided the same day: **one RTAB-Map session and segmentation run per drone**. Switching pauses
the previous drone's processing and keeps its map. Switching back resumes it. Inactive drones
keep flying unprocessed.

## Technical Changes

### State A (Current)

- **The bridge.** `bevy_bridge.BevyStreamSession` is one connection's state:
  - `hello` builds one backend from `profile_sensor_yaml`;
  - each `pair` becomes `process_frame`;
  - the reply is `encode_status(...)`.

  `serve_bevy_bridge(host, port, session_factory)` serves it over `websockets`. Only tests start
  it.
- **The wire** (`wire.rs` / `bevy_wire.py`): `hello` carries the camera and ground truth; `pair`
  carries `frame_id`, `t_ns`, size, `gray8` and `pose_enu`. There is **no drone or session id**.
  Goldens are `hello.bin` and `pair.bin`.
- **The Rust stream is never sent.** `encode_hello` / `encode_pair` are uncalled, and the wasm
  client is the open todo `bevy-live-websocket-stream` (M6).
- **RTAB-Map.** `StreamingRtabmapBackend` keeps its map **in memory for the life of the sidecar
  process**, using its own visual odometry. `Odom/ResetCountdown: 1` resets odometry after a gap,
  which starts a new sub-map in the same graph.
- **SAM.** The seam is `surmap.survey.sam.SamDetector` (`InMemorySamDetector` fake). The agent
  process still requires `--sam-fake` (`agent-cli-sam-flags` todo).
- **CI.** The `rtabmap-e2e` job builds the streaming image and runs
  `tests/test_bevy_sim_rtabmap_e2e.py` with `SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1`.
- **After n2–n4:** the page has an active drone, the eyes follow it, and frames carry `drone_id`
  in recordings. The page has a `?fleet=` link. `FleetTools` exists.

### State B (Target)

#### Wire

- `pair` header gains `"drone_id": "nest-sw-d1"` when the page has a fleet. It is absent
  otherwise (serde `skip_serializing_if`), so `pair.bin` is byte-identical.
- `hello` gains an optional `"scenario"`.
- `status` gains `"drone_id"`.
- A new golden, `pair-drone.bin`, is checked by both languages.

#### Station: `FleetPerception` (one per bridge connection)

- **`hello`** stores the camera profile and the scenario, and registers the router in
  `PerceptionRegistry[scenario]`.
- **`pair`** is routed by `drone_id`, or `"default"` when it is absent:
  1. Get or create that drone's `DroneSession`. Creating one makes a backend through the factory.
     At most `MAX_DRONE_SESSIONS = 4` exist at once; a fifth drone gets a status
     `error: "drone session limit (4) reached; <id> not processed"`.
  2. Call `backend.process_frame(pair)` and `segmentation.submit(frame_id, t_ns, left)`, then
     update that drone's counts.
  3. Mark it as the processing drone.
  4. Reply with a status for that drone.
- **Other drones' sessions get nothing** while another drone is active: they are idle, with their
  backend alive. Their frames, when they come again, go to the same backend. Expect RTAB-Map to
  report a reset and a new sub-map on resume (documented, asserted with the real sidecar only as
  "keyframes keep growing").
- **On close**, every session is finished: backends closed and recorders finished, in drone-id
  order.
- **`SamSegmentationSink`** runs the detector on the left frame with the run's concept prompt
  (default `"person"`) in a worker thread with a queue of 2 (drop oldest). It counts frames
  segmented and detections.

#### Agent

- `--bevy-bridge-port <port>` starts `serve_bevy_bridge` with a `FleetPerception` per connection.
  Each one uses the streaming RTAB-Map factory and the configured SAM detector (the fake under
  `--sam-fake`).
- `DroneMapStatus { scenario_id, optional drone_id }` returns, per drone: `frames`, `posed`,
  `lost`, `keyframes`, `segmented_frames`, `detections`, `processing`, `last_t_ns`. With no
  connected bridge page for the scenario it returns `UNAVAILABLE`.

#### Page

- `?bridge=ws://host:port` opens a binary `WebSocket` and sends `hello` at scene ready.
- `StreamPacer` decides each sim-time tick at `rate_hz`. On a send, it reads back the eyes
  (`Readback`, as `record.rs` does) and calls `encode_pair` with `ActiveDrone`'s id. When
  `bufferedAmount` exceeds 4 frame sizes it drops the pair instead.
- The status replies drive a line under the feed panel:
  `MAP nest-sw-d1 · 412 frames · 37 keyframes · tracking`.

### Delta (What's Changing)

#### surmap

- New `src/surmap/simulation/fleet/perception.py`. Changed: `bevy_wire.py`, `bevy_bridge.py`,
  `agent/__main__.py` (flag), `agent/server/app.py` (bridge lifecycle as a closeable).
- Changed n4-owned files, adding beside them: `proto/surmap/agent/v1/fleet_tools.proto` (rpc +
  messages) + generated code, `agent/tools/fleet_handlers.py` (one handler).
- Tests: `tests/test_fleet_perception.py`, `tests/test_bevy_wire.py` (drone id, goldens),
  `tests/test_fleet_perception_e2e.py` (loopback bridge, two drones),
  `tests/test_fleet_perception_rtabmap_e2e.py` (real sidecar), and
  `tests/test_agent_fleet_tools.py` (status case).
- `.github/workflows/ci.yml`: the `rtabmap-e2e` pytest line gains the new e2e file.

#### examples/bevy-sitl-poc

- `wire.rs` (`drone_id`). New `fleet/stream.rs`, `fleet/bridge_wasm.rs`. `ui.rs` (the map status
  line). `Cargo.toml` (`web-sys` `BinaryType`, `MessageEvent` if not already in).

## Verification

Three rungs, one per behaviour.

**1. Routing, wire and maps — V1 fail→pass.**
- Router tests with fake backends and sinks.
- Wire goldens in both languages.
- A loopback e2e over `serve_bevy_bridge` with two drones.
- A **real-sidecar** e2e in CI. It feeds the committed `tests/fixtures/bevy_sim_capture` frames as
  two drones in alternating blocks (A, B, A). Both sessions must produce keyframes, and A's
  backend must be the same object, with counts continuing after the switch back.
- The status tool's handler and service test.

**Command:** `uv run pytest -q tests/test_fleet_perception.py tests/test_fleet_perception_e2e.py tests/test_bevy_wire.py tests/test_agent_fleet_tools.py`,
`SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1 uv run pytest -q tests/test_fleet_perception_rtabmap_e2e.py`
(CI `rtabmap-e2e`), and `cd examples/bevy-sitl-poc && cargo test --locked stream wire`
**Before:** the new tests fail on the stubs; the old wire goldens pass. **After:** all pass, and
`hello.bin` / `pair.bin` stay byte-identical.

**2. The wasm stream compiles — V3.**
**Command:** `cd examples/bevy-sitl-poc && cargo check --locked --target wasm32-unknown-unknown`.
The before-output is recorded in commit 2; after, it passes with `fleet/bridge_wasm.rs`.

**3. The browser stream — V4.** No CI harness runs WebGPU readback in a browser.
**Approved:** the developer, 2026-11-04.

Procedure:

1. `trunk build index.html --release`.
2. Start the agent with `--sim-dist … --bevy-bridge-port 8773 --sam-fake`, with the streaming
   image available.
3. Open `/sim/?scenario=<earthquake-fleet>&fleet=1&bridge=ws://127.0.0.1:8773` in Chrome.
4. Through the chat (or `scripts/fleet_link_smoke.py`):
   1. launch `nest-sw-d1` and `nest-ne-d1`, with `nest-sw-d1` active for 60 s;
   2. `set_active_drone nest-ne-d1` for 60 s;
   3. switch back for 30 s;
   4. call `drone_map_status`.
5. Evidence: screenshots of the status line before and after each switch, and the
   `drone_map_status` output. It must show two drones with keyframes, `processing` on the active
   one, and `nest-sw-d1`'s frames continuing (not restarting) after the switch back.

## Acceptance Tests

- `test_two_drones_frames_go_only_to_their_own_map`
- `test_a_drone_switched_back_continues_in_the_same_map`
- `test_segmentation_runs_only_on_the_processed_drones_left_frames`
- `test_a_frame_without_a_drone_id_is_processed_as_before`
- `test_a_fifth_drone_is_refused_and_the_first_four_keep_working`
- `test_closing_the_page_finishes_every_drone_session`
- `test_drone_map_status_reports_every_drone`
- `test_two_real_rtabmap_sessions_both_map_and_one_resumes` (real sidecar, CI)
- Rust: `a_pair_carries_the_active_drones_id`, `a_pair_without_a_fleet_is_byte_identical_to_the_golden`,
  `the_pacer_sends_at_the_camera_rate_of_sim_time`, `the_pacer_drops_when_the_link_is_backed_up`

## Prerequisites

| Item | Verdict |
|---|---|
| `todo/2026-11-03-bevy-live-websocket-stream.md` | ⚠ during — this node delivers its wasm client and the status overlay. Its `scripts/serve_bevy_sim.py` is replaced by the agent's `--bevy-bridge-port` plus `--sim-dist` on one server. Resolved at wrap (Wrap TODO) |
| `todo/2026-11-03-agent-cli-sam-flags.md` | ⚠ during — real SAM in the agent process is still blocked. Segmentation is built on `SamDetector` and proven with `InMemorySamDetector`. Not fixed here (the PRD's Out of Scope) |
| `todo/2026-11-03-streaming-sidecar-lens-models.md` | ℹ the sim's pinhole profile is what the sidecar supports; unaffected |
| `todo/2026-11-03-bevy-loop-closure-acceptance.md` | ℹ the resume claim ("joins on revisit") is not asserted beyond keyframes growing, for the same reason that todo is open (capture too large to commit) |
| `code-issues/oversized-file-demo-server.md` | ⚠ during — nothing lands in `demo/server.py`; the router lives in `simulation/fleet/` |
| `code-issues/private-reach-agent-tools-workspace.md` | ⚠ during — no `DemoWorkspace` / `DemoRunHost` use; per-drone sessions are not runs |

Nothing blocks.

## Decisions & Trade-offs

- **Per-drone backends kept alive, not one multi-session map.** The developer chose "one map per
  drone". The sidecar's map lives in its process, and there is no save/load or append in the C++
  today. Keeping the process alive is the only honest way to make switching back resume.
  Resources are bounded by `MAX_DRONE_SESSIONS = 4` (one sidecar each).
- **Resume means the same graph, possibly a new sub-map.** The maps use visual odometry only (as a
  real drone would). The frame gap resets odometry, and the pieces join on loop closure. Feeding
  the simulation's pose as odometry would make the sim easier than flight, and §2.3's contract
  forbids that difference.
- **Per-drone sessions are not `RunHistoryStore` runs.** Making them runs would go through
  `DemoRunHost`'s single engine and the private-reach code issue. `get_run` / `find_objects` over
  per-drone maps is a follow-up, filed at wrap if wanted.
- **The page sends only the active drone.** Rendering and reading back several drones' eyes per
  frame would cost the GPU N× for frames nobody processes.
- **Complexity 5** is a boundary warning. The wasm streaming client could be split from the
  station router. They were kept together because `drone_id` on the wire has to be proven from
  both ends in one place (goldens), the same reason as n3's.
- **`[G]` on Sonnet only** (developer, 2026-11-04, whole stack): Sonnet · high, the effort mapping
  for complexity 5.
