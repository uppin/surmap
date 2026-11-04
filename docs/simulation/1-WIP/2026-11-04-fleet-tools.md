# Changeset: the survey agent flies the simulation's fleet

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — a new proto service and its contract (eight rpcs, the error mapping),
registration across `app.py` / `binding.py` / `services.py`, a skill and prompt change, and a
model-driven e2e over the real server with a fake simulation; one package

PRD: `PRD-2026-11-04-fleet-tools.md` · Discovery: `2026-11-04-fleet-tools-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-pr-stack` Plan — PRD, changeset, initial discovery · these files (`/plan-pr-stack` pass 1) · commit 1 `0959e1d`
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 46 failing (14 acceptance + 32 unit) — commit 2
  - [x] Build and baseline healthy (`uv run mypy`, `uv run pytest -q`, `cargo test --locked`)
  - [x] Stubs this node owns (`fleet_tools.proto` + generated code, `agent/tools/fleet_handlers.py`, `services.fleet_module`)
  - [x] Acceptance tests written and failing for the right reason
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes (`[G]` on Sonnet only — see Stack Context) ·
  - [ ] `proto/surmap/agent/v1/fleet_tools.proto`: `FleetTools` with `ListNests`, `ListDrones`, `LaunchDrone`, `SetRoute`, `AddDetour`, `RecallDrone`, `SetActiveDrone`, `GetFleetLog` (each SYNC · 10 s · FAIL, leading comments, field comments); `PROTOS += "fleet_tools"`; regenerated `_pb2`/`.pyi`/descriptor set
  - [ ] `agent/tools/fleet_handlers.py`: `fleet_tool_handlers(store, registry)` and its pure helpers (`fleet_error`, `flight_route`, `fleet_command`, `drone_phase`, `fleet_nest`, `drone_statuses` — see `## Validation Results`); error mapping (unknown scenario/drone → `NOT_FOUND`, `FleetInvalid` → `INVALID_ARGUMENT`, `FleetRefused` → `FAILED_PRECONDITION`, `FleetUnavailable` → `UNAVAILABLE`, `FleetTimeout` → `DEADLINE_EXCEEDED`)
  - [ ] Registration: `services.fleet_module`, `app.build_agent_description` (handlers, contracts, module — only with a `SimulationRig`), `binding._HANDLER_SERVICES`
  - [ ] Skill `agent/skills/flying-the-fleet/SKILL.md`; `using-the-map/SKILL.md` and the SYSTEM_PROMPT name the simulation-only exception
  - [ ] Gates green
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/agent.md` — `FleetTools` rows in the tool catalogue, a *Fleet tools* section (fields, errors, the simulation-only rule); the passive statements at 112, 181–182, 290 amended
  - [ ] `docs/simulation/changelog/2026-11-04-fleet-tools.md`
  - [ ] `src/surmap/docs/todo/` — new TODO: mirror fleet routes and drone markers onto the chat map (`MapSceneStore`, `enu_to_wgs84`)
  - [ ] Validate tests (`/validate-tests`)
  - [ ] Lint (`ruff --no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-04-fleet-tools-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Stack Context

**Stack**: drone nests and an agent-tasked simulated fleet · slug **`#drone-fleet`** — this PR is
**4 of 5** · [#120](https://github.com/uppin/surmap/pull/120)
**Branch**: `pr-4-drone-fleet` · **Base**: `pr-3-drone-fleet`
**Successor**: `pr-5-drone-fleet`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = `/plan-red` Steps 7–9 (stubs, failing acceptance + unit tests)
**Workflow override**: `[G]` (the Green row) runs on **Sonnet only**, instead of the
`/yolo-pr-stack` rubric's Haiku column. Effort comes from this node's complexity: 1–2 low,
3 medium, 4–5 high. A `[G]` retry stays on Sonnet, one effort step up, and never goes to Opus.
`[W]`/`[F]` keep the default rubric. Approved by the developer, 2026-11-04, for the whole
`#drone-fleet` stack. See `## Decisions & Trade-offs`.

Why the boundary falls here: the agent's surface is a proto service plus handlers, the same seam
as `SimulationTools` and `MapTools`. It is a thin client of n3's controller and owns nothing
below it.

### Owned API surface

- `proto/surmap/agent/v1/fleet_tools.proto`:
  - service `FleetTools` with rpcs `ListNests`, `ListDrones`, `LaunchDrone`, `SetRoute`,
    `AddDetour`, `RecallDrone`, `SetActiveDrone`, `GetFleetLog`;
  - messages `FleetNest`, `DroneStatus`, `DronePhase` (enum), `FlightRoute`, `RouteEnd` (enum),
    `FleetCommandResult`, and the request/response pairs;
  - generated `fleet_tools_pb2.py` / `.pyi`.
- `agent/tools/fleet_handlers.py` (`fleet_tool_handlers(store, registry)` and the pure helpers
  `fleet_error`, `flight_route`, `fleet_command`, `drone_phase`, `fleet_nest`, `drone_statuses`),
  `services.fleet_module`, registration
  in `app.py` / `binding.py`.
- Skill `flying-the-fleet`; the simulation-only sentences in `using-the-map` and the SYSTEM_PROMPT.

### Green wave

**Wave:** 3 of 3
**Node:** n4
**Concurrent with:** n5
**Blocks:** n5 at compile level only. n5 adds `DroneMapStatus` to this service's proto and
registers its handler beside these, so it needs the file and the module to exist, not their
behaviour.

Real dependency edges, as opposed to the branch line:

    n1 → n2, n3      n2 → n5      n3 → n4      n4 → n5 (compile only: n5 adds an rpc to n4's service)

### Greenable independently?

**no — blocked by n3** (`pr-3-drone-fleet`). Every handler test drives a real `FleetRegistry` /
`FleetController` linked to n3's fake simulation client (`tests/fleet_fakes.py`). While n3 is
stubbed, `send` raises `NotImplementedError`, and a test red for that reason is blocked on n3.

### Trunk-merge safety

**When this PR merges alone:** additive. `FleetTools` is registered only when the server has a
`SimulationRig`, beside `SimulationTools`. With no linked page, every command answers
`UNAVAILABLE` with the reason. The agent server starts, and `uv run pytest -q` passes. **Local dev
data:** none. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `FleetRegistry`, `FleetController.send/drones/active/session_log`, `FleetInvalid/Refused/Unavailable/Timeout` | n3 | stub, `TODO(pr-3)` | calls them; maps their errors to Connect codes |
| `fleet.commands` (`Launch`, `SetRoute`, `Detour`, `Recall`, `SetActive`, `Route`) | n3 | stub, `TODO(pr-3)` | builds them from requests |
| `FleetLogStore.export_jsonl` | n3 | stub | `get_fleet_log` returns it |
| `SimulationRig.fleet` | n3 | stub | registration reads it |
| `tests/fleet_fakes.py` fake simulation client | n3 | test helper | tests link it to the registry |
| `fleet_nests.nests_of` | n1 | (green by then) | `list_nests` and `list_drones` read it from the scenario's latest manifest (`ScenarioStore.scenario`) — the controller keeps its nests private |

**Greenable independently?** no — needs n3 green first.

## Background

The developer (2026-11-04): "The agent should also be able to activate a drone, plan its trip
route (on auto-pilot), adjust the route mid-course, do detours etc. … (the agent would decide
which one [is on screen])". n1 wrote the simulation-only scope exception, n2 flies the drones and
n3 carries commands live. This node is the agent's hands.

## Technical Changes

### State A (Current)

- **How a tool service is wired:**
  1. A proto in `proto/surmap/agent/v1/`, with `default_execution` options and leading comments
     as tool descriptions.
  2. `scripts/gen_agent_rpc.py` `PROTOS` and checked-in generated code.
  3. A handler factory of `(request, ctx)` closures that raise `ConnectError(Code.X, msg)`
     (`simulation_handlers.py`, `map_handlers.py`).
  4. `services.py` `xxx_module`.
  5. Registration in `app.build_agent_description` and `binding._HANDLER_SERVICES` (`:37`). Rpc
     names are one global namespace.
- **Positions** use `EnuPoint { east, north, up }` (`simulation_tools.proto`).
- **The scope wording.** `using-the-map/SKILL.md:9-12` says no map tool commands a vehicle, and
  the agent declines flight and navigation. The SYSTEM_PROMPT (`app.py:116-117`) mirrors the
  passive scope.
- **Tests:**
  - handler-level `call(handlers, "Rpc", pb.Req(...))`;
  - e2e through `ScriptedChatModel` + `build_agent_description` on `HypercornHost` port 0;
  - `a_tool_rig` / `a_chat_rig` builders.
- **After n3:** `SimulationRig.fleet: FleetRegistry`, and `FleetController` with its typed errors,
  commands and log export.

### State B (Target)

#### `FleetTools` (all SYNC · 10 s · FAIL)

| rpc | Request | Response |
|---|---|---|
| `ListNests` | `scenario_id` | `repeated FleetNest { id, EnuPoint position, yaw_deg, repeated drone_ids }` |
| `ListDrones` | `scenario_id` | `linked`, `active`, `repeated DroneStatus { id, nest, DronePhase phase, EnuPoint position, yaw_deg, speed_m_s, targets_left }` (from the last telemetry; without a link, every drone is `DOCKED` at its pad and `linked: false`) |
| `LaunchDrone` | `scenario_id`, `drone_id`, `FlightRoute route { repeated EnuPoint waypoints; optional float speed_m_s; RouteEnd on_complete (RETURN default, HOVER) }` | `FleetCommandResult { seq, at_s }` |
| `SetRoute` | same as `LaunchDrone` | `FleetCommandResult` |
| `AddDetour` | `scenario_id`, `drone_id`, `repeated EnuPoint waypoints` | `FleetCommandResult` |
| `RecallDrone` | `scenario_id`, `drone_id` | `FleetCommandResult` |
| `SetActiveDrone` | `scenario_id`, `drone_id` | `FleetCommandResult` |
| `GetFleetLog` | `scenario_id`, `optional session_id` (latest when absent) | `session_id`, `fleet_log_jsonl` |

Errors:

| Condition | Code |
|---|---|
| unknown scenario or drone | `NOT_FOUND` |
| `FleetInvalid` | `INVALID_ARGUMENT`, with the rule |
| `FleetRefused` (the page's reason) | `FAILED_PRECONDITION` |
| `FleetUnavailable` | `UNAVAILABLE` |
| `FleetTimeout` | `DEADLINE_EXCEEDED` |

The service's header comment states the scope: "These tools task the **simulation's** drones on
machine 3 only; nothing here reaches PX4 or any real flight controller."

#### Skill `flying-the-fleet`

Its procedure:

1. Call `list_nests` and `list_drones`. Without a link, ask the person to open the scenario page
   with `?fleet=1` (give the URL).
2. Plan waypoints over the scene from `get_scenario` (clear of building footprints, 5–60 m up,
   speed ≤ 8 m/s).
3. Launch, then confirm with `list_drones`.
4. Use `add_detour` for a closer look and `set_route` to re-plan.
5. Call `set_active_drone` on the drone whose camera matters now. Only the active drone's feed is
   on screen and processed.
6. Recall when done, and `get_fleet_log` for a replay.

The skill also says what to do on each error.

#### Wording

- **SYSTEM_PROMPT:** "Simulated drones in the station's simulation can be tasked with the fleet
  tools. Real aircraft are never commanded."
- **`using-the-map`:** a drawn route is still never a flight plan. For a *simulated* drone, use
  the fleet tools. For a real vehicle, decline.

### Delta (What's Changing)

#### surmap

- New: `proto/surmap/agent/v1/fleet_tools.proto` + generated `src/surmap/agent/proto/fleet_tools_pb2.py`/`.pyi`
  and the descriptor set; `src/surmap/agent/tools/fleet_handlers.py`;
  `src/surmap/agent/skills/flying-the-fleet/SKILL.md`.
- Changed: `scripts/gen_agent_rpc.py`, `src/surmap/agent/services.py`,
  `src/surmap/agent/server/app.py`, `src/surmap/agent/server/binding.py`,
  `src/surmap/agent/skills/using-the-map/SKILL.md`.
- Tests: `tests/test_agent_fleet_tools.py` (handlers, the pure helpers and the `FleetTools`
  contract), `tests/test_agent_fleet_tools_e2e.py` (scripted model on the real server, fake
  simulation linked), and their shared station `tests/fleet_tool_fakes.py`.

## Verification

**Method:** V1 fail→pass — handler tests over a real `FleetRegistry` linked to n3's fake
simulation client, plus a model-driven e2e through the real agent server.
**Command:** `uv run pytest -q tests/test_agent_fleet_tools.py tests/test_agent_fleet_tools_e2e.py`
**Before:** fails — the `FleetTools` rpcs are stubs (`UNIMPLEMENTED`) and the helpers raise
`NotImplementedError`; the linked-page tests also wait on n3's `serve_fleet_link` stub. Commit 2
records the output (`## Validation Results`).
**After:** all pass. The `FleetTools` contract tests (every rpc a described SYNC · 10 s · FAIL
tool) and the registration test already pass on the red tree.

## Validation Results

**Baseline (`0959e1d`: n1 green, n2 and n3 red, this node's planning):** `uv run mypy` clean (522
files), `ruff check --no-cache` / `ruff format --no-cache --check` clean; `uv run pytest -q` 2237
passed, 70 failed, 38 skipped — all inherited: n2's 1
(`test_bevy_capture.py::test_a_fleet_capture_names_the_drone_on_every_frame`) and n3's 69
(`test_sim_fleet_controller.py` 38, `test_sim_fleet_link.py` 17, `test_sim_fleet_link_e2e.py`
14); `cargo test --locked` 286 passed, 62 failed — n2's 44 + n3's 18 (this node has no Rust).

**Red tree (commit 2):** `uv run pytest -q` 2240 passed, 116 failed, 38 skipped — 70 inherited +
46 new; the 3 new passing tests are the `FleetTools` contract (`test_every_fleet_tool_is_a_quick_call_that_fails_on_timeout`,
`test_every_fleet_tool_is_described_to_the_model`) and the registration
(`test_with_a_simulation_the_model_is_offered_the_fleet_tools`), real on the red tree because the
proto and the registration are. `mypy` (527 files), `ruff check --no-cache`, `ruff format
--no-cache --check` clean. `cargo test` unchanged.

Failing tests (46 = 14 acceptance + 32 unit/integration), and what each is red on:

- **Red on n3's stub** (14) — every test that links the fake page: the `/sim/fleet` upgrade answers
  HTTP 500 because `fleet_routes.serve_fleet_link` is `TODO(pr-3)`. Their n4 failure is behind
  it; they go green only once n3 and n4 both are (the declared `blocked by n3`):
  `tests/test_agent_fleet_tools.py` — `test_the_agent_launches_a_drone_and_hears_when_it_took_off`
  (:140), `test_a_new_route_and_a_detour_reach_an_airborne_drone` (:158),
  `test_a_detour_for_a_docked_drone_fails_naming_its_phase` (:182),
  `test_a_recalled_drone_is_reported_docked` (:195), `test_set_active_drone_changes_the_active_drone`
  (:212), `test_an_invalid_route_is_refused_with_the_rule` ×4 (:281), `test_the_fleet_log_comes_back_as_a_replay_file`
  (:295), `test_an_unknown_drone_is_not_found` (:363), `test_a_command_the_page_refuses_fails_with_the_page_s_reason`
  (:375), `test_a_page_that_never_answers_fails_the_command_past_its_deadline` (:390);
  `tests/test_agent_fleet_tools_e2e.py` — `test_a_scripted_conversation_flies_a_sortie_through_the_agent_server` (:79).
- **Red on n4's stub, then still needing n3's controller** (3) — `UNIMPLEMENTED` today; green they
  call `FleetController.linked` / `send` / `drones`: `test_without_a_linked_page_commands_fail_unavailable`
  ×2 (:240), `test_without_a_linked_page_drones_report_unlinked_and_docked_at_their_pads` (:253).
- **Red on n4's stub only** (29) — `UNIMPLEMENTED` or `NotImplementedError("pr-4: implement")`;
  n4's green alone turns them: `test_list_nests_names_each_pad_and_its_drones` (:325),
  `test_an_unknown_scenario_is_not_found` ×3 (:352), and the pure helpers —
  `test_each_fleet_failure_answers_its_connect_code` ×5 (:460), `test_an_invalid_command_s_message_leads_with_its_rule`
  (:468), `test_a_refusal_keeps_the_page_s_reason_word_for_word` (:479), `test_a_flight_route_becomes_the_fleet_s_route`
  (:493), `test_a_route_without_speed_or_end_leaves_the_simulation_s_defaults` (:503),
  `test_a_route_ending_in_return_says_so` (:511), `test_each_command_request_becomes_its_fleet_command`
  ×5 (:535), `test_each_telemetry_phase_is_reported_as_its_drone_phase` ×7 (:560),
  `test_a_nest_is_reported_with_its_pad_heading_and_drones` (:579),
  `test_drones_with_no_telemetry_are_docked_on_their_pad_facing_its_heading` (:589),
  `test_a_drone_in_the_telemetry_is_reported_as_the_page_saw_it` (:597).

No test is blocked on n1 or n2. Wave unchanged (3 of 3, after n3).

Red-step notes — shapes the tests pin, which `[G]` must honour:

- **Handlers.** `fleet_tool_handlers(store: ScenarioStore, registry: FleetRegistry)`, not
  `(registry)`: n3's `FleetController` keeps its nests private and `FleetRegistry` its store, so
  nests and pads come from `nests_of(store.scenario(id).manifest)`. The handler resolves the
  scenario through the store **first** — an unknown one is `NOT_FOUND` naming it, for every rpc,
  before the registry is touched. Registration is real: `app.build_agent_description` builds them
  over `simulation.store` / `simulation.fleet`, mounts `services.fleet_module` beside
  `SimulationTools` and binds the `FleetTools` contracts, all only with a `SimulationRig`;
  `binding._HANDLER_SERVICES` includes `surmap.agent.v1.FleetTools`.
- **Pure helpers** in `fleet_handlers.py`, each tested directly: `fleet_error(FleetError) ->
  ConnectError` — `FleetInvalid` with `UNKNOWN_DRONE` → `NOT_FOUND`, any other rule →
  `INVALID_ARGUMENT` with message `"<rule.value>: <the station's message>"`, `FleetRefused` →
  `FAILED_PRECONDITION` with the reason verbatim, `FleetUnavailable` → `UNAVAILABLE`,
  `FleetTimeout` → `DEADLINE_EXCEEDED` (the last two keep `str(error)`); `flight_route(FlightRoute)
  -> Route` (absent `speed_m_s` → `None`; `ROUTE_END_UNSPECIFIED` → `None`, `RETURN` → `"return"`,
  `HOVER` → `"hover"`); `fleet_command(CommandRequest) -> FleetCommand` for the five command
  requests; `drone_phase(Phase) -> DronePhase`; `fleet_nest(Nest) -> FleetNest`;
  `drone_statuses(nests, telemetry)` — every drone nest by nest in drone order, as telemetry
  reports it, else docked at its pad with the pad's yaw (speed 0, nothing left to fly). Without a
  link `ListDrones` passes no telemetry.
- **The phase is named.** `test_a_detour_for_a_docked_drone_fails_naming_its_phase` needs the
  message to start `not_flying` **and** contain `docked`. n3 does not pin `FleetInvalid`'s message
  text; if its message does not name the phase, the handler must (e.g. append the drone's phase
  from `drone_statuses`).
- **Proto.** `ListDronesResponse` has `linked`, `active` (empty when none), `drones` — **no
  `sim_t_s`**: n3's controller exposes no telemetry time (only `drones()` / `active()`), and n4
  may not change it. Add it when the controller exposes one (a follow-up for `[W]` to file).
  Enums are prefixed (`DRONE_PHASE_*`, `ROUTE_END_*`) with `_UNSPECIFIED = 0`;
  `FlightRoute.speed_m_s` is `optional double`; `GetFleetLogRequest.session_id` is `optional
  int32` (latest session when absent). `FleetCommandResult { int32 seq; double at_s }`.
- **Without a link** only commands a docked drone accepts (`launch`, `set_active`) reach the
  `UNAVAILABLE` answer: n3 validates before it checks the link, so `set_route` / `add_detour` /
  `recall_drone` on a docked drone answer `INVALID_ARGUMENT` first. The PRD's "every command
  fails with no simulation connected" is read as every command that passes validation.
- **E2E** runs two chat turns in one conversation (`fleet-1`): turn 1 `list_nests` →
  `launch_drone`; the page then reports nest-sw-d1 cruising; turn 2 `add_detour` →
  `set_active_drone`. A tool answer is the JSON of its response (proto field names).
- **Test station.** `tests/fleet_tool_fakes.py` (`a_fleet_station`, `FleetStation.call` /
  `a_linked_page` / `reports` / `turn`) is this node's; it reuses n3's `tests/fleet_fakes.py`
  unchanged. The skill `flying-the-fleet` and the wording changes have no test (Green TODOs).

## Acceptance Tests

- `test_the_agent_launches_a_drone_and_hears_when_it_took_off`
- `test_a_new_route_and_a_detour_reach_an_airborne_drone`
- `test_a_detour_for_a_docked_drone_fails_naming_its_phase`
- `test_a_recalled_drone_is_reported_docked`
- `test_set_active_drone_changes_the_active_drone`
- `test_without_a_linked_page_commands_fail_unavailable` (launch, set active) and
  `test_without_a_linked_page_drones_report_unlinked_and_docked_at_their_pads`
- `test_an_invalid_route_is_refused_with_the_rule` (empty, altitude, speed, bounds)
- `test_the_fleet_log_comes_back_as_a_replay_file`
- e2e: `test_a_scripted_conversation_flies_a_sortie_through_the_agent_server`

## Prerequisites

| Item | Verdict |
|---|---|
| `todo/2026-11-03-agent-tool-image-parts.md` | ℹ unrelated here; the fleet tools return text and data only |
| `code-issues/private-reach-agent-server-hub.md` | — unrelated; no hub change |
| `code-issues/private-reach-agent-tools-workspace.md` | — unrelated; no `DemoWorkspace` use |

Nothing blocks.

## Decisions & Trade-offs

- **A service of its own, not more `SimulationTools` rpcs.** `SimulationTools` edits stored
  scenarios. `FleetTools` acts on a running page. Their failure modes (no page, timeouts) and
  their scope sentence differ, and the split keeps each service's contract honest.
- **SYNC · 10 s · FAIL, not DETACH.** A command is acknowledged within 5 s (n3's timeout). The
  flight itself is observed with `list_drones`, not awaited by a job.
- **ENU waypoints, not lon/lat.** They are the same frame as the scene the agent built with
  `SimulationTools` (`EnuPoint`). The chat map mirror (lon/lat) is a follow-up TODO.
- **`[G]` on Sonnet only** (developer, 2026-11-04, whole stack): Sonnet · high instead of the
  rubric's Haiku · xhigh for complexity 4.
