# Changeset: Agent station lifecycle — on-demand SAM GPU, station tools, UI indicator

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — proto contract change (new `StationTools` service, Python + TS gen), more than one package (`surmap.agent`, `surmap.survey`, `web/agent-chat`), an SDK adapter seam, idle timing / concurrency

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery companion
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests, committed · Python: 4 suites red on missing modules; UI: 1 suite unresolved + 3 App tests red
  - [x] `tests/test_agent_station.py` — the `StationControl` contract over the stub: states, start/stop, idempotence, idle stop, first-use start
  - [x] `tests/test_agent_station_modal.py` — `ModalStationControl` over a fake Modal function: status from stats, start probes health, stop closes the link and scales down, idle stop
  - [x] `tests/test_agent_station_tools.py` — the three tools' contracts (policies, descriptions) and handlers; tools absent without a station
  - [x] `tests/test_agent_server_app.py` — `--station stub|modal` config; SAM runs through the station without `--sam-fake`
  - [x] `web/agent-chat` — `StationIndicator` vitest (states, Start/Stop, hidden without a station); App wiring; e2e over the stub server
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · pytest 2143 passed (1 pre-existing local RTAB-Map e2e timeout, also red on #112's tip); vitest 124/124; e2e 11/11; mypy, ruff, tsc, lint, build green
  - [x] `proto/surmap/agent/v1/station_tools.proto` + Python gen (`scripts/gen_agent_rpc.py`) + TS gen (`yarn gen`)
  - [x] `surmap.agent.tools.station`: `StationState`, `StationStatus`, `StationControl`, `StubStationControl`, `StationSamDetector`
  - [x] `surmap.agent.tools.station_modal`: `ModalFunction` protocol, `ModalStationControl`, `modal_station_function()` (the only `modal` import)
  - [x] `station_tool_handlers`, `station_tools_module`; mounted in `build_agent_description` only with a station
  - [x] Config + CLI: `--station {stub,modal}`, `--station-app`, `--station-env`, `--station-idle-s`, `--station-prompt`; `pyproject` optional extra `modal`
  - [x] UI: `ChatPort` station methods, Connect adapter, `StationIndicator` in the header, e2e stub server
- [wf 4] ⏳ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (V1 suites; V4 live run)
  - [ ] `docs/agent.md` — station tools, `--station`, chat header indicator
  - [ ] `docs/modal.md` §5 — the station as a deployed scale-to-zero app the agent drives
  - [ ] Changelog entry; TODO `src/surmap/docs/todo/2026-11-03-agent-cli-sam-flags.md` resolved (deleted) or narrowed
  - [ ] TODO record for the station-side idle close of foreign sockets (rpc layer)
  - [ ] Lint and quality gates green (Python four; `yarn lint`, `yarn typecheck`, `yarn test --run`, `yarn build`)
  - [ ] (optional) Production readiness validated — run, the change reaches server code and a cloud adapter

## Initial Discovery

Full codebase exploration that grounded this plan:
[initial-discovery.md](./2026-11-04-agent-station-lifecycle-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Stack Context

Node 2 of 2, on `deploy-station-modal-rpc-ee7bd1e1` (#112, the Modal station fixes).

### Inherited Dependencies — do not implement here

- `StationSettings`, the GPU fallback and the prompt reaching the container (#112). This node's
  live verification deploys the station those fixes produce.

## Affected Packages

- `surmap` — `agent/tools`, `agent/server`, `agent/__main__`, `agent/services`, `agent/proto`,
  `proto/surmap/agent/v1`, `scripts/gen_agent_rpc.py`, `pyproject.toml` (optional extra).
- `web/agent-chat` — ports, Connect adapter, header component, gen, e2e stub.

## Related Feature Documentation

- [docs/agent.md](../../agent.md) · [docs/modal.md](../../modal.md) · PRD:
  [PRD-2026-11-04-agent-station-lifecycle.md](./PRD-2026-11-04-agent-station-lifecycle.md)

## Summary

The agent can see, start and stop a SAM GPU station, its SAM runs on it, the GPU comes up on first
use and goes down 5 minutes after the last, and the chat header shows the state with Start / Stop.

## Background

See the PRD. The station works on Modal (#112); the agent cannot reach it.

## Scope

In: PRD R1–R6. Out: closing sockets other clients hold open (TODO record), `surmap-sam`, workspace
choice in the UI, a GPU name in the status (Modal stats do not report it).

## Technical Changes

### State A (Current)

- Agent SAM: `CentredBoxVideoSamDetector`, `--sam-fake` mandatory. No station or Modal code in the agent.
- Station on Modal: `modal serve`/`deploy` by hand; stays up `scaledown_window` (300 s) after the
  last request; nothing reports or controls it.
- UI header: title, server URL, nav, model picker.

### State B (Target)

- **Interface** (`surmap.agent.tools.station`):
  `StationState` (`OFF`, `QUEUED`, `STARTING`, `READY`, `STOPPING`, `ERROR`);
  `StationStatus(state, detail, containers, idle_timeout_s, idle_for_s, backend)`;
  `StationControl` protocol — `status()`, `start()`, `stop()`, `detector()`.
- **`StationSamDetector(control, connect)`** — the `VideoSamDetector` the workspace gets: the first
  `track()` calls `control.start()`, then delegates to the connected detector; marks use.
- **`StubStationControl(clock, start_s=…, idle_timeout_s=300)`** — deterministic state machine on
  an injected clock; detector = fake centred box behind `StationSamDetector`.
- **`ModalStationControl(function, probe, connect, token, prompt, clock, idle_timeout_s)`** over a
  `ModalFunction` protocol (`get_current_stats`, `update_autoscaler`, `get_web_url`):
  - status — stats only: no runners and no backlog → `OFF` (or `STOPPING` until gone), backlog with
    no runner → `QUEUED`, runners before a healthy probe → `STARTING`, after → `READY`;
  - start — `update_autoscaler(scaledown_window=idle)`, then `probe(url)` until 200 (a GET is a
    Modal input: it boots a container) → `READY`;
  - stop — close the agent's station link, `update_autoscaler(min_containers=0, scaledown_window=2)`
    → `STOPPING` → `OFF` once no runner is left;
  - idle — `check_idle()` stops it `idle_timeout_s` after the last SAM frame; a daemon ticker calls
    it in the process, tests call it directly.
  - `modal_station_function(app, environment)` — the one place `modal` is imported (`importlib`),
    returning the protocol.
- **Tools** (`proto/surmap/agent/v1/station_tools.proto`, service `StationTools`):
  `GetStationStatus` (SYNC 10 FAIL), `StartStation` (SYNC 30 DETACH), `StopStation` (SYNC 30 DETACH),
  each answering `StationStatusResponse`; mounted with a station only.
- **Process**: `--station stub|modal`, `--station-app` (default `surmap-station`), `--station-env`,
  `--station-idle-s` (300), `--station-prompt` (default `object`, the run's prompt wins);
  `--sam-fake` not required with a station. `pyproject`: `[project.optional-dependencies] modal`.
- **UI**: `ChatPort.getStationStatus / startStation / stopStation`; `StationIndicator` beside the
  model picker: `SAM · <state>` + Start / Stop, polled every 5 s, hidden on `Unimplemented`.

### Delta (What's Changing)

#### surmap

+ `agent/tools/station.py`, `agent/tools/station_modal.py`, `agent/tools/station_handlers.py`,
`proto/.../station_tools.proto` + gen; edits to `app.py`, `__main__.py`, `services.py`,
`gen_agent_rpc.py`, `pyproject.toml`.

#### web/agent-chat

+ `components/StationIndicator.tsx` (+ test); edits to `ports.ts`, `adapters/connect-chat.ts`,
`ChatPage.tsx`, `App.test.tsx`, `e2e/stub-chat-server.ts`, `e2e/chat.spec.ts`, `src/gen/**`.

## Verification

**Method:** V1-fail→pass — acceptance tests over the stub and a fake Modal function (Python), the
component and e2e tests (UI); V4 — one live run against Modal.
**Command:** `uv run pytest -q tests/test_agent_station*.py tests/test_agent_server_app.py` ·
`cd web/agent-chat && yarn test --run && yarn e2e`
**Before:** the new tests fail (no `surmap.agent.tools.station`, no `StationTools`, no indicator).
**After:** all pass.

V4 (the SDK and the GPU are only reachable on Modal): 1. `modal deploy` the station on `ginas-bb`;
2. `python -m surmap.agent --station modal` + the chat page; 3. the header reads `SAM · off` and
`uvx modal container list` is empty; 4. **Start** → `starting` → `ready`, one container; 5. a
`prompt_sam` turn runs on the station; 6. **Stop** → `off`, no container; 7. a run after 5 min
idle (`--station-idle-s 60` for the check) ends with no container; 8. `modal app stop`.
Evidence: screenshots, tool replies, container lists.
**Approved:** pending — asked before the run (a deploy persists until stopped).

## Decisions & Trade-offs

- Status reads Modal stats, never the station's HTTP: a poll must not start a GPU or reset its
  scaledown window. Readiness comes from the controller's own health probe at start.
- Stop is `min_containers=0, scaledown_window=2` plus closing the agent's own link, not the private
  `ContainerStop` API. A socket another client holds open keeps the container until that client
  closes it — the out-of-scope TODO.
- The idle timer lives in the agent (it knows its last SAM frame); with stop as above the GPU goes
  down `idle_timeout_s` after the last frame, not idle + scaledown.
- Complexity 5 on purpose: the user chose one feature PR after the fixes PR.
- `modal` is an optional extra imported in one function; everything else sees `ModalFunction`.

## Validation Results

(filled by the Wrap row)
