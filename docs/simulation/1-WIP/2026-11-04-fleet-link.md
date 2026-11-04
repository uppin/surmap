# Changeset: the fleet link — the station commands the running simulation's drones

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — two languages and a wire contract (`fleet/v1` goldens), async request/ack
with timeouts and one-connection-per-scenario ordering, a new WebSocket route on the agent server,
SQLite persistence, and a wasm-only `web-sys` client no CI harness can run

PRD: `PRD-2026-11-04-fleet-link.md` · Discovery: `2026-11-04-fleet-link-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-pr-stack` Plan — PRD, changeset, initial discovery · these files (`/plan-pr-stack` pass 1) · commit 1 `d6fb7dc`
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 87 failing (32 acceptance + 55 unit) — commit 2
  - [x] Build and baseline healthy (`uv run mypy`, `uv run pytest -q`, `cargo test --locked`)
  - [x] Stubs this node owns (`surmap.simulation.fleet` package, `agent/server/fleet_routes.py`, Rust `fleet/link.rs`, `fleet/link_wasm.rs`)
  - [x] Acceptance tests written and failing for the right reason
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes (`[G]` on Sonnet only — see Stack Context) ·
  - [ ] Goldens `tests/fixtures/fleet_link/{hello,command,applied,refused,telemetry}.json`; Rust `fleet/link.rs` codec and Python `fleet/link.py` codec both round-trip them
  - [ ] Python `fleet/commands.py`: typed commands (`Launch`, `SetRoute`, `Detour`, `Recall`, `SetActive`, `Route`) whose JSON equals n2's `tests/fixtures/fleet/commands.json`
  - [ ] Python `fleet/controller.py`: `FleetController` (station-side checks mirroring n2's refusals, request ids, 5 s ack timeout, latest telemetry, applied log) and `FleetRegistry` (scenario → controller; one link per scenario)
  - [ ] Python `fleet/log_store.py`: `fleet_sessions` + `fleet_log` tables in the scenario store's SQLite file; `export_jsonl(session)` in n2's `--fleet-log` format
  - [ ] Agent server: `WebSocketRoute("/sim/fleet", …)` in the description when a `SimulationRig` is configured; `SimulationRig.fleet: FleetRegistry`
  - [ ] Rust `fleet/link_wasm.rs` (`cfg(target_arch = "wasm32")`): `?fleet=1` → `web_sys::WebSocket` to `/sim/fleet?scenario=<id>`; inbound commands queued, drained into `FleetLog::push` at `SimClock::now()`; `applied`/`refused` sent back; telemetry every 0.5 s; `web-sys` features added
  - [ ] `scripts/fleet_link_smoke.py`; `Cargo.toml` description and `index.html` banner say what the link sends
  - [ ] Gates green; `cargo test --locked`; `cargo check --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (V1 suites; V3 wasm check output; V4 Chrome procedure with the smoke script's log and a screenshot)
  - [ ] `docs/simulation/bevy-simulation.md` — *The fleet link* (`fleet/v1` messages, `?fleet=1`, the log store, the smoke script)
  - [ ] `docs/agent.md` — `/sim/fleet` in the server's routes
  - [ ] `docs/simulation/changelog/2026-11-04-fleet-link.md`
  - [ ] Validate tests (`/validate-tests`)
  - [ ] Production readiness validated (`/validate-prod-ready`) — new server route and persistence
  - [ ] Lint (`ruff --no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-04-fleet-link-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Stack Context

**Stack**: drone nests and an agent-tasked simulated fleet · slug **`#drone-fleet`** — this PR is
**3 of 5** · [#119](https://github.com/uppin/surmap/pull/119)
**Branch**: `pr-3-drone-fleet` · **Base**: `pr-2-drone-fleet`
**Successor**: `pr-4-drone-fleet`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = `/plan-red` Steps 7–9 (stubs, failing acceptance + unit tests)
**Workflow override**: `[G]` (the Green row) runs on **Sonnet only**, instead of the
`/yolo-pr-stack` rubric's Haiku column. Effort comes from this node's complexity: 1–2 low,
3 medium, 4–5 high. A `[G]` retry stays on Sonnet, one effort step up, and never goes to Opus.
`[W]`/`[F]` keep the default rubric. Approved by the developer, 2026-11-04, for the whole
`#drone-fleet` stack. See `## Decisions & Trade-offs`.

Why the boundary falls here: the link is a wire contract, and both of its ends belong in one PR
so the goldens have one owner. The agent tools (n4) are a thin client of the controller. The
autopilot (n2) only receives commands through `FleetLog::push`.

### Owned API surface

- Python `surmap.simulation.fleet`:
  - `link.py`: `encode_command`, `decode_sim_message` → `SimHello | Applied | Refused | Telemetry`,
    `DroneTelemetry`, `FleetLinkError`.
  - `commands.py`: `Route`, `Launch`, `SetRoute`, `Detour`, `Recall`, `SetActive`, `FleetCommand`.
  - `controller.py`:
    - `FleetController`: `send(command) -> Applied`, `drones()`, `active()`, `session_log()`,
      `attach` / `detach`.
    - Errors: `FleetUnavailable`, `FleetRefused(reason)`, `FleetInvalid(rule)`, `FleetTimeout`.
    - `FleetRegistry`: `controller(scenario_id)`, `link(scenario_id, socket)`.
  - `log_store.py`: `FleetLogStore` (`record`, `sessions`, `export_jsonl`).
- Agent server: `agent/server/fleet_routes.py` (`fleet_websocket_route`), `SimulationRig.fleet`.
- Rust: `fleet/link.rs` (`LinkMessage`, `decode_station`, `encode_hello`, `encode_applied`,
  `encode_refused`, `encode_telemetry`), `fleet/link_wasm.rs` (`FleetLinkPlugin`, `?fleet=` parse).
- Fixtures: `tests/fixtures/fleet_link/*.json`. Script: `scripts/fleet_link_smoke.py`.

### Green wave

**Wave:** 2 of 3
**Node:** n3
**Concurrent with:** n2
**Blocks:** n4 (its tools call `FleetController.send` / `drones` and need a real controller
answering through a linked sim)

Real dependency edges, as opposed to the branch line:

    n1 → n2, n3      n2 → n5      n3 → n4      n4 → n5 (compile only: n5 adds an rpc to n4's service)

### Greenable independently?

**no — blocked by n1** (`pr-1-drone-fleet`). The controller's drone-id and bounds checks read
nests through n1's `fleet_nests.nests_of`, and the acceptance tests build the `earthquake-fleet`
preset. Tests still red on `TODO(pr-1)` are blocked on n1.

The Rust codec decodes into n2's `FleetCommand` types. Those are plain serde data, so they are
real even while n2's behaviour is stubbed. The Python side tests against a **fake simulation
client** that answers `applied` with a scripted `at_s`, not against n2's autopilot, so n2 is not
a behaviour dependency. The wasm glue that calls n2's `FleetLog::push` is proven only by the V4
run, after n2 is green.

### Trunk-merge safety

**When this PR merges alone:** additive.

- The WebSocket route exists only when the server has a `SimulationRig`. Nothing connects unless
  a page opens with `?fleet=1`.
- The two new tables are created on demand in the scenario store's SQLite file, and existing rows
  are untouched.
- The wasm build gains `web-sys` features only.
- `uv run pytest -q`, `cargo test`, `trunk build` and the agent server's start keep working.

**Local dev data:** the scenario DB gains two tables on first use, and there is no migration of
existing rows. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `fleet_nests.nests_of`, `Nest`, preset `earthquake-fleet` | n1 | stub, `TODO(pr-1)` | the controller reads nests and drone ids from it |
| `FleetCommand`, `Route`, `OnComplete` (Rust serde types) | n2 | data types real; behaviour stubbed `TODO(pr-2)` | decodes `command` messages into them |
| `FleetLog::push`, `Fleet` resource, `Phase` names | n2 | stub, `TODO(pr-2)` | the wasm glue calls `push` at `SimClock::now()`; telemetry reads `Fleet` |
| `tests/fixtures/fleet/commands.json`, `--fleet-log` format | n2 | committed fixture | Python commands must serialise to it; `export_jsonl` writes the format |

**Greenable independently?** no — needs n1 green first (nests).

## Background

The developer (2026-11-04) wants the agent to activate drones, plan their routes, and adjust them
"mid-course". Discovery found no channel into a running simulation at all:

- the page reads the manifest and `?scenario=` once;
- the Rust wire format is encode-only and never sent;
- `Cargo.toml` and `index.html` promise "nothing is sent to a backend".

This node builds the missing link. The scope decision of the same day
(`docs/architecture.md` §1, written in n1) bounds it to the simulation.

## Technical Changes

### State A (Current)

- The agent server serves `/sim/` (the trunk `dist`), `/sim/assets/scenarios/<id>.json` (the
  latest manifest version, `no-store`) and the assets, all over GET (`agent/server/sim_routes.py`;
  `SimulationRig` holds `store`, `sources`, `static_assets`, `page_dist`).
- `surmap.rpc.description` supports `WebSocketRoute(path, handler(context))`, and `HypercornHost`
  mounts `description.websocket_routes` (`rpc/hosts/hypercorn.py:79-80`). The agent description
  does not use it today.
- The page reads only `?scenario=` (`shots.rs::page_scenario`). Its wasm `web-sys` features are
  `Window` and `Location` only.
- The Python `websockets` dependency is in use (`bevy_bridge.serve_bevy_bridge`).
- `ScenarioStore` keeps versioned manifests in SQLite.
- After n1, nests and drone ids exist. After n2, the renderer has `FleetLog::push`, `Phase`, the
  `Fleet` resource and the `--fleet-log` format.

### State B (Target)

#### `fleet/v1` messages (JSON text frames)

| Direction | Message |
|---|---|
| sim → station | `{"type":"hello","protocol":"fleet/v1","scenario":"…","sim_t_s":0.0,"drones":["nest-sw-d1",…]}` |
| station → sim | `{"type":"command","request":7,"command":{…n2's FleetCommand…}}` |
| sim → station | `{"type":"applied","request":7,"seq":3,"at_s":41.25}` |
| sim → station | `{"type":"refused","request":7,"at_s":41.25,"reason":"nest-sw-d1 is docked: detour needs a drone in flight"}` |
| sim → station | `{"type":"telemetry","sim_t_s":41.5,"active":"nest-sw-d1","drones":[{"id":"…","phase":"cruising","enu":[x,y,z],"yaw_deg":…,"speed_m_s":…,"targets_left":2}]}` every 0.5 s |

- An unknown `type`, or a protocol other than `fleet/v1`, closes the socket with code 4400.
- A second link for a scenario that already has one is closed with code 4409.

#### Station

- **`FleetRegistry`** lives on `SimulationRig.fleet`, one per server. `controller(id)` builds a
  `FleetController` from the scenario's latest manifest (its nests) on first use.
- **`FleetController.send(command)`** runs in this order:
  1. **Validate.** The drone must be known. The route must be non-empty, every waypoint within
     ±500 m east/north and 5–60 m up, and the speed 0.5–8 m/s. The phase from the last telemetry
     must allow the command (n2's rules). A failure raises `FleetInvalid(rule)`.
  2. **No link** raises `FleetUnavailable("no simulation connected for scenario <id>")`.
  3. **Send and wait** up to 5 s for `applied` or `refused` with the same request id. `applied`
     is recorded in `FleetLogStore` and returned as `Applied(seq, at_s)`. `refused` raises
     `FleetRefused(reason)`. No answer raises `FleetTimeout`.

  Requests are serialised per scenario, so the order sent is the order applied.
- **`FleetLogStore`** writes to the scenario DB file. `fleet_sessions` holds `session_id`,
  `scenario_id`, `started_at` and `hello`. `fleet_log` holds `session_id`, `seq`, `at_s` and
  `command_json`. `export_jsonl(session)` writes n2's `--fleet-log` lines.
- **The route.** `fleet_routes.fleet_websocket_route` reads `?scenario=`, requires a `hello`
  first, starts a session, then pumps messages to the controller until close. Close detaches the
  link, so later sends fail with `FleetUnavailable`.

#### Renderer

- **Pure.** `fleet/link.rs` holds `decode_station(&str) -> Result<StationMessage, LinkError>` and
  the `encode_*` functions.
- **wasm only.** `fleet/link_wasm.rs`:
  - `page_fleet_enabled()` reads `?fleet=1`.
  - `FleetLinkPlugin` opens `WebSocket(ws[s]://<location.host>/sim/fleet?scenario=<id>)` and
    sends `hello` once the scene is built.
  - `onmessage` pushes onto a shared queue. A Bevy system drains it each frame: it calls
    `FleetLog::push(SimClock::now(), command)` and sends `applied` / `refused`.
  - A timer system sends telemetry every 0.5 s.
- **Native** has no link. `--fleet-log` remains the native input.
- `Cargo.toml` and `index.html` change "nothing is sent to a backend" to say frames stay in the
  page and the optional `?fleet=1` link exchanges fleet commands and telemetry.

### Delta (What's Changing)

#### surmap

- New `src/surmap/simulation/fleet/` (`__init__.py`, `link.py`, `commands.py`, `controller.py`,
  `log_store.py`); new `src/surmap/agent/server/fleet_routes.py`; `sim_routes.py`
  (`SimulationRig.fleet`); `app.py` (websocket route in the description).
- New `scripts/fleet_link_smoke.py`.
- Tests: `tests/test_sim_fleet_link.py` (codec + goldens), `tests/test_sim_fleet_controller.py`,
  `tests/test_sim_fleet_link_e2e.py` (a real `HypercornHost` on port 0 and a fake sim client over
  `websockets`), with fakes in `tests/fleet_fakes.py`.

#### examples/bevy-sitl-poc

- New `fleet/link.rs`, `fleet/link_wasm.rs`; `Cargo.toml` (`web-sys` features `WebSocket`,
  `MessageEvent`, `CloseEvent`, `ErrorEvent`; description); `index.html` (banner).

## Verification

Three rungs, one per behaviour.

**1. Station and codec — V1 fail→pass.** Acceptance tests over a real agent server and a fake
simulation client, controller unit tests, and the codec against the goldens in both languages.
**Command:** `uv run pytest -q tests/test_sim_fleet_link.py tests/test_sim_fleet_controller.py tests/test_sim_fleet_link_e2e.py`
and `cd examples/bevy-sitl-poc && cargo test --locked link`
**Before:** all fail on the stubs. **After:** all pass.

**2. The wasm client compiles — V3.**
**Command:** `cd examples/bevy-sitl-poc && cargo check --locked --target wasm32-unknown-unknown`
**Before:** recorded in commit 2 (the check passes without the link module, which does not exist
yet). **After:** the same command passes with `fleet/link_wasm.rs` compiled in.

**3. The browser link — V4.** No CI harness runs a WebGPU page with a live WebSocket
(`bevy-visual-checkpoints-v3-v5` todo: the browser runtime is unverified in CI).
**Approved:** the developer, 2026-11-04.

Procedure:

1. `cd examples/bevy-sitl-poc && trunk build index.html --release`.
2. `uv run python scripts/fleet_link_smoke.py --sim-dist examples/bevy-sitl-poc/dist --preset earthquake-fleet`.
   The script prints the page URL and waits for a `hello`.
3. Open the printed `/sim/?scenario=<id>&fleet=1` in Chrome.
4. The script sends a sortie: `launch` `nest-sw-d1`, a `detour` at +15 s, `set_active`
   `nest-ne-d1` after launching it, then `recall` both. It prints each `applied` (`seq`, `at_s`)
   and the telemetry phases.
5. Evidence to capture: the script's full log, a screenshot with two drones airborne and the feed
   on `nest-ne-d1`, and the exported `--fleet-log` file. Replaying that file natively
   (`--screenshot … --at <t>`) must show the same drone positions as the browser at the same
   simulation time.

## Validation Results

**Baseline (`d6fb7dc`: n1 green, n2 red, this node's planning):** `uv run mypy` clean (512
files), `ruff check --no-cache` / `ruff format --no-cache --check` clean; `uv run pytest -q` 2237
passed, 1 failed, 38 skipped — the 1 is n2's `test_bevy_capture.py::test_a_fleet_capture_names_the_drone_on_every_frame`
(inherited); `cargo test --locked` 286 passed, 44 failed — all 44 n2's (`fleet::tests::*`,
`shots::tests::a_fleet_log_flag_*`, inherited).

**V3 before-output** (`cargo check --locked --target wasm32-unknown-unknown`, before
`link_wasm.rs` existed): `warning: bevy-sitl-poc (bin "bevy-sitl-poc") generated 47 warnings` ·
``Finished `dev` profile [optimized + debuginfo] target(s) in 3.13s``. On the red tree the same
command compiles with the `link_wasm` stub in (its only new warnings: the stubs are never used).
No `web-sys` feature was needed for the stub, so `Cargo.toml` / `Cargo.lock` are unchanged; Green
adds `WebSocket`, `MessageEvent`, `CloseEvent`, `ErrorEvent`.

**Red tree (commit 2):** `uv run pytest -q` 2237 passed, 70 failed, 38 skipped — 1 inherited + 69
new; `cargo test --locked` 286 passed, 62 failed — 44 inherited + 18 new. `mypy` (522 files),
`ruff check --no-cache`, `ruff format --no-cache --check` clean; `cargo test --locked --no-run`,
`cargo build --locked` and the wasm check compile.

Why each fails: Python — `NotImplementedError("pr-3: implement")` in every new test (55 direct;
the 14 e2e tests through `fleet_routes.serve_fleet_link`, which makes Hypercorn answer the
upgrade with HTTP 500, or through `FleetController`); Rust — `todo!("pr-3: implement")` in
`fleet/link.rs` (17). **Blocked on n2:** `fleet::link::tests::the_station_export_is_a_valid_fleet_log`
panics in n2's `FleetLog::from_jsonl` (`TODO(pr-2)`); it passes once n2 is green (and needs
`from_jsonl` to accept the seq gap 1 → 3 a live refusal leaves). No test is blocked on n1 (green
in this tree). Wave unchanged.

Tests (87 = 32 acceptance + 55 unit):

- Acceptance, `tests/test_sim_fleet_link_e2e.py` (14): `test_a_linked_simulation_applies_a_launch_and_the_scenario_logs_it`,
  `test_a_command_the_simulation_refuses_returns_its_reason_and_is_not_logged`,
  `test_an_invalid_command_is_refused_without_reaching_the_simulation` ×6 (unknown drone, empty
  route, speed, altitude, bounds, phase), `test_without_a_linked_page_a_command_reports_no_simulation_connected`,
  `test_after_the_page_closes_a_command_reports_no_simulation_connected`,
  `test_a_silent_page_times_out_after_five_seconds`, `test_telemetry_is_what_the_controller_reports`,
  `test_a_second_page_for_the_same_scenario_is_refused`, `test_the_stored_log_exports_as_a_fleet_log_file`.
- Acceptance, codec: `tests/test_sim_fleet_link.py` (11: each sim golden decodes ×4 and
  re-encodes byte-identically ×4, the command golden, commands serialise to and parse from n2's
  `commands.json`); `fleet/link/tests.rs` (7: the command golden decodes and re-encodes, hello /
  applied / refused / telemetry goldens, `the_station_export_is_a_valid_fleet_log`).
- Unit: `tests/test_sim_fleet_link.py` (6: unknown command type, five non-`fleet/v1` frames);
  `tests/test_sim_fleet_controller.py` (38: one per `FleetInvalid` rule ×14, docked before
  telemetry, limits valid, no link, applied stamp, frame sent, request numbering, serialised
  sends, refusal, 5 s timeout, detach, telemetry ×2, registry ×7, log store ×5);
  `fleet/link/tests.rs` (11: unknown type, malformed ×2, phase words, drone telemetry, refusal
  texts ×3, `?fleet=1`, `ws`/`wss` URL ×2).

Red-step notes — shapes the tests pin, which `[G]` must honour:

- **Frames** are compact JSON (`separators=(",", ":")`), keys in State B's order; a golden file is
  the frame plus one trailing newline (tests strip it). `command.json` carries n2's
  `commands.json[0]` (the launch, every route field present, so Rust's serde re-encodes it
  byte-identically). The goldens use scenario `quake-fleet` (`create_scenario("Quake fleet",
  "earthquake-fleet")`) and its five drones.
- **Python commands.** `Route(waypoints, speed_m_s: float | None = None, on_complete: "return" |
  "hover" | None = None)` — `None` is omitted from the JSON (so `set_route` matches the fixture);
  `command_json(command) -> dict` and `parse_command(mapping) -> FleetCommand` (`ValueError`
  naming an unknown type) live in `commands.py`; `Stamped(seq, at_s, command)` too.
- **Link.** `decode_sim_message` → `SimHello(scenario, sim_t_s, drones)`, `Applied(request, seq,
  at_s)`, `Refused(request, at_s, reason)`, `Telemetry(sim_t_s, active, drones)` with
  `DroneTelemetry(id, phase, enu, yaw_deg, speed_m_s, targets_left)`; `encode_sim_message` is its
  inverse; `FleetLinkError` for not-JSON, unknown type, other protocol, missing field, unknown
  phase. Phase words: `docked climbing cruising detouring hovering returning landing`. Close codes
  `CLOSE_PROTOCOL_ERROR = 4400`, `CLOSE_ALREADY_LINKED = 4409` — the route accepts the upgrade,
  then closes (never a handshake refusal).
- **Controller.** `FleetController(scenario_id, nests, log_store, *, timing: FleetTiming)`;
  `FleetTiming(ack_timeout_s=5.0, sleep=asyncio.sleep)` is the injected clock (the timeout tests
  assert one `sleep(5.0)` and no real wait). `attach(link: SimLink, hello)` starts a log session;
  `receive(SimMessage)`; `detach()` fails a waiting send with `FleetUnavailable`; `linked`,
  `session_id`, `drones()` (empty before telemetry), `active()`, `session_log()`. Requests start
  at 1; a second send is not written until the first is answered. Before any telemetry every
  drone counts as `docked`. `FleetInvalid.rule` is `InvalidRule` (`UNKNOWN_DRONE`, `NO_WAYPOINTS`,
  `SPEED_OUT_OF_RANGE`, `HEIGHT_OUT_OF_RANGE`, `OUT_OF_BOUNDS`, `NOT_DOCKED`, `NOT_FLYING`,
  `ALREADY_DOCKED` — n2's `RefusalReason` plus the bounds); the limits themselves (0.5 / 8 m/s,
  5 / 60 m, ±500 m) are valid. `FleetUnavailable` says `no simulation connected for scenario <id>`.
- **Registry.** `FleetRegistry(store, *, timing)` exposes `log_store` (a `FleetLogStore` on
  `store.db_path`, a new read-only `ScenarioStore` property); `controller(id)` is cached;
  `async link(scenario_id, socket: SimSocket)` runs one page (`receive_text() -> str | None`,
  `send_text`, `close(code)`). `SimulationRig` gained `fleet_timing` (default `FleetTiming()`)
  and `fleet` (`init=False`, built in `__post_init__`), so existing constructions are unchanged.
- **Route.** `fleet_websocket_route(rig)` is real and already mounted by `build_agent_description`
  when a `SimulationRig` is given; only `serve_fleet_link(registry, scope, receive, send)` is the
  stub. `WebSocketRoute.handler` now returns `Callable[..., Awaitable[None]]` (an ASGI app takes
  three arguments; the old one-argument type had no user).
- **Log store.** `start_session(scenario_id, hello) -> int`, `record(session_id, Stamped)`,
  `sessions(scenario_id)` oldest first (`FleetSession(session_id, scenario_id, started_at,
  hello)`), `entries(session_id)` in `at_s` order (`UnknownSession` for an unknown id),
  `export_jsonl(session_id)` with `json.dumps` default separators — byte-identical to n2's
  `--fleet-log` files; the station-export fixture is `tests/fixtures/fleet_link/session.fleet.jsonl`
  (seqs 1 and 3: the page refused request 2).
- **Rust.** `StationMessage::Command { request, command }` and `LinkMessage` are serde data;
  `LinkError::{UnknownType(String), Malformed(String)}`; `encode_hello(scenario, sim_t_s,
  &[String])`, `encode_applied(request, seq, at_s)`, `encode_refused(request, at_s, reason)`,
  `encode_telemetry(sim_t_s, Option<&str>, &[DroneTelemetry])`; `phase_name(Phase)` (n2's
  `Phase` has no serde, and this node does not change it); `drone_telemetry(id, &DroneState)`
  (`speed_m_s` = |velocity|, `targets_left` = current target + `legs_left`); `refusal_text(&command,
  &RefusalReason)` (e.g. `nest-sw-d1 is docked: detour needs a drone in flight`,
  `… is cruising: launch needs a docked drone`, `nest-zz-d9 is not a drone of this scene`);
  `fleet_enabled(search)` (only `fleet=1`) and `fleet_socket_url(page_protocol, host, scenario)`
  are pure so the wasm glue stays thin. `link_wasm.rs` (`page_fleet_enabled`, `FleetLinkPlugin {
  scenario }`) is not added to the app until Green.

## Acceptance Tests

- `test_a_linked_simulation_applies_a_launch_and_the_scenario_logs_it`
- `test_a_command_the_simulation_refuses_returns_its_reason_and_is_not_logged`
- `test_an_invalid_command_is_refused_without_reaching_the_simulation` (unknown drone, empty
  route, speed, altitude, bounds, phase)
- `test_without_a_linked_page_a_command_reports_no_simulation_connected`
- `test_a_silent_page_times_out_after_five_seconds` (clock injected)
- `test_telemetry_is_what_the_controller_reports`
- `test_a_second_page_for_the_same_scenario_is_refused`
- `test_the_stored_log_exports_as_a_fleet_log_file` (and Rust parses it: `the_station_export_is_a_valid_fleet_log`)
- Codec: every golden decodes and re-encodes byte-identically in Python and Rust; Python
  commands serialise to n2's `commands.json`.

## Prerequisites

| Item | Verdict |
|---|---|
| `todo/2026-11-03-bevy-live-websocket-stream.md` | ⚠ during — same page, different socket. This node adds the `web-sys` WebSocket features and the `?param=` parsing pattern n5 reuses for `?bridge=`; it does not close the todo (n5 does) |
| `todo/2026-11-03-bevy-visual-checkpoints-v3-v5.md` | ℹ the reason V4 is needed: the browser runtime has no CI check |
| `todo/2026-11-03-non-agent-clients-on-fake-servers.md` | — unrelated (agent clients) |
| `code-issues/private-reach-agent-server-hub.md` | — unrelated; the fleet route does not touch `hub.py` |

Nothing blocks.

## Decisions & Trade-offs

- **The simulation stamps time, and the station keeps the stamped copy.** Only the page knows
  simulation time. The station's log mirrors the `applied` answers, so the replay file is the
  page's truth and not the station's guess.
- **The station validates as well as the simulation.** The agent gets a precise
  `INVALID_ARGUMENT`-grade reason without a round trip. The page still refuses on its own phase
  (telemetry is up to 0.5 s old).
- **A separate socket from the stereo bridge (n5).** Commands are small, latency-sensitive JSON on
  the agent server's own origin. Frames are bulk binary to the bridge port. Sharing one socket
  would let frame backpressure delay a recall.
- **One link per scenario.** Two pages would each run their own autopilot and disagree. The second
  is refused, not silently ignored.
- **Complexity 5** is a boundary warning. Splitting the Rust client from the station was weighed
  and rejected: the wire goldens would then have two owners, and neither half could prove the
  contract alone.
- **`[G]` on Sonnet only** (developer, 2026-11-04, whole stack): Sonnet · high instead of the
  rubric's Sonnet · medium for complexity 5. The model is unchanged and effort is one step up, per
  the effort mapping in Stack Context.
