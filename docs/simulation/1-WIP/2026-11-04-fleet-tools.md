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

- [wf 1] ✅ 2026-11-04 `/plan-pr-stack` Plan — PRD, changeset, initial discovery · these files (`/plan-pr-stack` pass 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Build and baseline healthy (`uv run mypy`, `uv run pytest -q`, `cargo test --locked`)
  - [ ] Stubs this node owns (`fleet_tools.proto` + generated code, `agent/tools/fleet_handlers.py`, `services.fleet_module`)
  - [ ] Acceptance tests written and failing for the right reason
  - [ ] Unit/integration tests written and failing
  - [ ] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes (`[G]` on Sonnet only — see Stack Context) ·
  - [ ] `proto/surmap/agent/v1/fleet_tools.proto`: `FleetTools` with `ListNests`, `ListDrones`, `LaunchDrone`, `SetRoute`, `AddDetour`, `RecallDrone`, `SetActiveDrone`, `GetFleetLog` (each SYNC · 10 s · FAIL, leading comments, field comments); `PROTOS += "fleet_tools"`; regenerated `_pb2`/`.pyi`/descriptor set
  - [ ] `agent/tools/fleet_handlers.py`: `fleet_tool_handlers(registry)`; error mapping (unknown scenario/drone → `NOT_FOUND`, `FleetInvalid` → `INVALID_ARGUMENT`, `FleetRefused` → `FAILED_PRECONDITION`, `FleetUnavailable` → `UNAVAILABLE`, `FleetTimeout` → `DEADLINE_EXCEEDED`)
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
**4 of 5** · `#pending`
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
- `agent/tools/fleet_handlers.py` (`fleet_tool_handlers`), `services.fleet_module`, registration
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
| `fleet_nests.nests_of` | n1 | (green by then) | `list_nests` reads it through the controller |

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
| `ListDrones` | `scenario_id` | `linked`, `sim_t_s`, `active`, `repeated DroneStatus { id, nest, DronePhase phase, EnuPoint position, yaw_deg, speed_m_s, targets_left }` (from the last telemetry; without a link, every drone is `DOCKED` at its pad and `linked: false`) |
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
- Tests: `tests/test_agent_fleet_tools.py` (handlers), `tests/test_agent_fleet_tools_e2e.py`
  (scripted model on the real server, fake simulation linked), and the contract test lists.

## Verification

**Method:** V1 fail→pass — handler tests over a real `FleetRegistry` linked to n3's fake
simulation client, plus a model-driven e2e through the real agent server.
**Command:** `uv run pytest -q tests/test_agent_fleet_tools.py tests/test_agent_fleet_tools_e2e.py`
**Before:** fails — the `FleetTools` rpcs are stubs (`UNIMPLEMENTED`). Commit 2 records the
output.
**After:** all pass. The existing agent contract tests (every rpc has a description and an
execution policy) pass with the new service included.

## Acceptance Tests

- `test_the_agent_launches_a_drone_and_hears_when_it_took_off`
- `test_a_new_route_and_a_detour_reach_an_airborne_drone`
- `test_a_detour_for_a_docked_drone_fails_naming_its_phase`
- `test_a_recalled_drone_is_reported_docked`
- `test_set_active_drone_changes_the_active_drone`
- `test_without_a_linked_page_commands_fail_unavailable_and_drones_report_unlinked`
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
