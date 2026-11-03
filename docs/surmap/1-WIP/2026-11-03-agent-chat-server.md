# Changeset: Survey agent chat server — `python -m surmap.agent`

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — server-streaming RPC with concurrent steer/cancel, wiring of four predecessors, socket e2e test

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (commit 1 `4a99a65`)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 78 failing — commit 2
  - [x] Create failing acceptance tests
  - [x] Run acceptance tests (verify they fail)
  - [x] TDD Red — write failing unit/integration tests
- [wf 3] ✅ 2026-11-03 `/green` Green — implement until every red test passes · 78/78 green, full suite green (1627 passed, 32 skipped) — commit 3
  - [x] Milestone 1: `ChatHub` — conversations, one `AgentSession` each, event fan-out to `StreamTurn` / `WatchConversation` subscribers
  - [x] Milestone 2: `ChatService` handlers (`StreamTurn`, `WatchConversation`, `Steer`, `CancelTurn`, `ListModels`, `GetConversation`) and runtime-event → `TurnEvent` mapping
  - [x] Milestone 3: tool binding — `SurveyTools` handlers (n7) + job tools (n4) as agent tools; tool images reach the chat stream, and the model reads their placeholder (model image parts are a recorded follow-up, see `Decided without review (green step)`)
  - [x] Milestone 4: HTTP routes (`/geometry`, `/frames`, `/health`), CORS
  - [x] Milestone 5: `surmap.agent.__main__` (flags, env, system prompt) on `HypercornHost`
  - [x] Acceptance: `tests/test_agent_chat_service.py`, `tests/test_agent_server_e2e.py` pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/agent.md` — "Running the agent" section: command, flags, env, ports, routes, event stream
  - [ ] `docs/deployment.md` — note the agent process and port 8780
  - [ ] `README.md` — "Survey agent" quick start
  - [ ] `docs/surmap/changelog/2026-11-03-agent-chat-server.md` — write changelog entry
  - [ ] Validate tests (`/validate-tests`)
  - [ ] Production readiness validated (`/validate-prod-ready`) — new long-running server process

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-agent-chat-server-initial-discovery.md](./2026-11-03-agent-chat-server-initial-discovery.md).

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **8 of 9** · [#84](https://github.com/uppin/surmap/pull/84)
**Branch**: `pr-8-survey-agent` · **Base**: `pr-7-survey-agent`
**Successor**: `pr-9-survey-agent`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance and unit tests

Why the boundary falls here: this is the composition root — the only node that wires protos (n1),
runtime (n4), models (n5) and tools (n7) into a process. Each of those is tested alone; this node
tests them together over Connect.

### Owned API surface

- `surmap.agent.server.hub`: `ChatHub(*, model_factory, tools, models, default_model_id,
  system_prompt, caps, timeout_scale)` (`get`, `stream_turn`, `watch`, `watchers`, `steer`,
  `cancel`, `runner`, `close`), `Conversation`, `ModelFactory`, `ToolFactory`, `ModelLister`
- `surmap.agent.server.chat_service`: `chat_handlers(hub)`, `agent_jobs_handlers(hub)`,
  `turn_event_to_proto(event, *, conversation_id, turn_id, seq)`, `CONVERSATION_HEADER`
- `surmap.agent.server.binding`: `agent_tools(contracts, handlers, runner, *, resolve)`,
  `ToolImage`, `IMAGE_KEY`
- `surmap.agent.server.routes`: `agent_http_routes(frames, geometry, *, cors_origins)`,
  `FrameReader`, `GlbReader`, `GLB_MEDIA_TYPE`, `HEALTH_PATH`
- `surmap.agent.server.app`: `AgentServerConfig` (real), `SYSTEM_PROMPT` (real),
  `build_agent_description(config, *, workspace, geometry, registry, survey_handlers)`,
  `default_model_factory(registry, ledger)`, `build_demo_workspace(config)`
- `surmap.agent.__main__`: `build_parser()` (real), `config_from_args(argv, environ)`,
  `serve(config)`, `main(argv)`

### Green wave

**Wave:** 3 of 4
**Node:** n8
**Concurrent with:** none — this node is alone in its wave
**Blocks:** n9 (the UI talks to this server)

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9
    n5-wrap → n8   (`MetaResponsesChatModel.before_call` lives in n5's wrap commit `7839755`,
                    which is on `pr-5-survey-agent` but not yet under `pr-6`…`pr-8`)

Edges found by the red step (6f): n1 and n4 are real on this base. n7 is reached only by the
frame-conversion route tests and the socket e2e; every other test injects fake `SurveyTools`
handlers. n5's registry is real, but the budget hook one test needs is not in this branch's
ancestry until the stack is restacked onto n5's tip.

### Greenable independently?

**no — blocked by n7 for 8 tests, and by n5's wrap commit for 1**: n1, n4 and n5 (`7a9e1bb`) are
green on this base. 69 of the 78 red tests need only this node's code: the chat-service tests
drive real `AgentSession` turns (n4) with `FakeToolHandler`s bound to the real `SurveyTools`
contracts (n1), so n7 is incidental to them.

| Blocked test | On | Why |
|---|---|---|
| `tests/test_agent_server_routes.py::test_a_png_frame_is_served_as_a_jpeg` | n7 | re-encodes through `frame_image` |
| `tests/test_agent_server_routes.py::test_a_frame_crop_returns_just_that_box` | n7 | crops through `frame_image` |
| `tests/test_agent_server_e2e.py` — all 6 tests | n7 | real `DemoWorkspace`, `survey_tool_handlers`, `GeometryStore` (the integration is the point) |
| `tests/test_agent_server_app.py::test_a_muse_model_with_its_budget_spent_refuses_before_sending` | n5 wrap `7839755` | `MetaResponsesChatModel.before_call` is not on this branch's ancestry yet |

Tests red for those predecessors are blocked, not failures.

### Trunk-merge safety

**When this PR merges alone:** a new entry point only; no existing process changes. **Local dev
data:** tests use a temp history DB. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `chat_service_module`, `agent_jobs_module`, `survey_tools_module`, `tool_contracts` | n1 | real after n1 green | mounts them |
| `AgentSession`, `JobRunner`, `bind_contract_tool`, `job_tools`, runtime events | n4 | real after n4 green | drives them; maps events |
| `ChatModelRegistry` | n5 | real after n5 green | builds the model; `ListModels` |
| `survey_tool_handlers`, `DemoWorkspace`, `GeometryStore` | n7 | real after n7 green | binds and serves them |

**Greenable independently?** no — 8 tests need n7 green and 1 needs n5's wrap commit restacked
under this branch (see `## Stack Context`).

## Inherited Restructure — expect rewrite

n2 moves the demo run engine; this node reaches it only through n7's `DemoWorkspace`. No direct
fallout expected.

## Affected Packages

- **surmap** (`src/surmap/agent/server`, `src/surmap/agent/__main__.py`).

## Related Feature Documentation

- PRD: [PRD-2026-11-03-agent-chat-server.md](./PRD-2026-11-03-agent-chat-server.md)

## Summary

A hypercorn process serving three Connect services and three HTTP routes, with a `ChatHub` that owns
one `AgentSession` per conversation and fans its events out to streaming subscribers.

## Background

`HypercornHost(desc, ctx, host, port).start()` with `ServerDescription(services, http_routes)` is the
existing pattern (`survey/station_main.py:77-92`); `InMemoryHost` gives in-process service tests.

## Scope

- Hub, service handlers, tool binding, HTTP routes, entry point, system prompt
- **Out of scope:** durable conversation storage, auth (loopback/dev only — documented)

## Technical Changes

### State A (Current)

No agent process. Connect hosting via `rpc/hosts/hypercorn.py`; plain HTTP routes via
`ServerDescription.http_routes`.

### State B (Target)

```text
browser ──Connect (fetch)──► hypercorn :8780
                               ├─ ChatService ── ChatHub ── AgentSession (n4) ── model (n5)
                               │                                   └─ JobRunner ── tools: SurveyTools handlers (n7) + job tools
                               ├─ AgentJobs   ── same runner
                               ├─ SurveyTools ── same handlers (direct calls from the UI)
                               └─ HTTP /geometry /frames /health
```

### Delta (What's Changing)

#### surmap

- `src/surmap/agent/server/{__init__,hub,chat_service,binding,routes,app}.py`, `src/surmap/agent/__main__.py` (new)

## Verification

**Method:** V1 — fail→pass service tests in process and one socket e2e
**Command:** `uv run pytest -q tests/test_agent_chat_service.py tests/test_agent_server_e2e.py`
**Before:** red (commit 2) — 78 failing, every one on this node's `NotImplementedError` in
`surmap.agent.server` / `surmap.agent.__main__`: the two acceptance files (25) plus
`tests/test_agent_chat_service_errors.py`, `tests/test_agent_server_{events,binding,routes,app}.py`
(53). Baseline before commit 2: 1504 passed, 9 skipped, 66 failed — all 66 n7's red tests
(`tests/test_agent_tools_{demo,frames,objects}.py`). 8 of this node's tests stay red until n7 is
green and 1 until n5's wrap commit is under this branch (`## Stack Context`).
**After:** green with a scripted model; a live run is recorded at wrap: `uv run python -m surmap.agent --sam-fake --model ollama:<m>` answering "what demos can you run?" (or why it was not run)

## Testing Plan

- `InMemoryHost` client: `server_stream("StreamTurn", …)`, concurrent `unary("Steer", …)` and `unary("CancelTurn", …)`.
- `ScriptedChatModel` (n4's fake) injected through `AgentServerConfig.model_factory`.
- Socket e2e: `HypercornHost` on port 0, `/health`, one `StreamTurn` over HTTP/1.1 Connect.

## Acceptance Tests

### surmap

- `tests/test_agent_chat_service.py` (19) — message/tool start/finish/text/finished sequence, text,
  result JSON, `STOP`, `seq` numbering across turns; steer during a blocking `run_demo` (accepted,
  detached to `j-1`, `steer_applied`, reply after it; not accepted when idle); idle job-event turn
  on `WatchConversation` (answer, opens with the job's `job_update`); cancel (`CANCELLED`, response,
  handler cancelled); `ListModels` (reachable + default, unreachable default listed unavailable);
  `GetConversation` replays the streamed events
- `tests/test_agent_server_e2e.py` (6) — real socket: `/health`, one streamed turn over HTTP/1.1
  Connect, the real `list_demos` result, CORS on a Connect response, GLB a glTF reader accepts,
  recorded frame as JPEG

Lower-tier red tests:

- `tests/test_agent_chat_service_errors.py` (8) — unknown provider `INVALID_ARGUMENT`, busy
  conversation `FAILED_PRECONDITION`, idle cancel, unknown conversation `NOT_FOUND`, tool images
  on the stream and out of the JSON, `AgentJobs` by `surmap-conversation-id` header
- `tests/test_agent_server_events.py` (16) — `turn_event_to_proto` for every runtime event
- `tests/test_agent_server_binding.py` (8) — `agent_tools`: names, runner, missing handler, JSON →
  request → JSON, `ConnectError` → failed, bad arguments, `ToolImage`
- `tests/test_agent_server_routes.py` (12) — health, GLB, frames (as recorded, PNG → JPEG, crop,
  400, 404s), CORS allow/deny/preflight
- `tests/test_agent_server_app.py` (9) — `config_from_args` defaults/flags/CORS env,
  `default_model_factory` budget refusal and usage ledger, system prompt, bound tools, direct
  `SurveyTools`, `/health`

## Decisions & Trade-offs

- **`WatchConversation` stream for idle events**: a server cannot push without an open stream; the
  UI keeps one per open conversation, and `StreamTurn` covers the turn it starts.
- **In-memory conversations**: survey sessions are short; durable storage is a follow-up TODO.
- **No auth; binds 127.0.0.1 by default** — the tools can start runs, so exposing it needs a deliberate `--host`.

### Decided without review (red step)

- **`StreamTurn` opens with the `user_message` event** (seq 1), so `GetConversation` replays
  exactly the streamed events.
- **A job-event turn opens with the ended job's `job_update`**, so the UI shows why it started.
- **`Steer` on an idle conversation is `accepted=false` and starts nothing**; the UI sends a
  `StreamTurn` instead (the runtime's idle-steer-starts-a-turn is not exposed).
- **Finish reasons**: `round_cap` → `LENGTH`, `repeated_failure` → `STOP` (the proto has no closer
  value).
- **`AgentJobs` names its conversation in the `surmap-conversation-id` header** — each
  conversation has its own `JobRunner`, and the jobs requests carry no conversation field.
- **Tool images**: the binding returns a response's `image` bytes as a `ToolImage` the model reads
  as `<image/jpeg, N bytes, shown to the user>` and the stream carries as `image`/`media_type`.
  Sending the image to the model as an image part needs runtime support (n4 builds tool messages
  as JSON text); recorded as a follow-up, not done here.
- **Ledger wiring**: `default_model_factory(registry, ledger)` gives a `meta:` model
  `ledger.check` as `before_call` and the ledger as its usage sink (the n5 wrap follow-up).
- **Seams**: `build_agent_description` takes the workspace, a `GlbReader` and optional registry
  and `SurveyTools` handlers; the routes take a `FrameReader` + `GlbReader` rather than the whole
  workspace, so they test without n7.

### Decided without review (green step)

- **Busy and steer state read `AgentSession._active`.** The session has no public probe for "a
  turn is running", so `ChatHub` reads the flag its own `run_turn` checks. Follow-up for n4: a
  public `is_running` property, so the hub stops reading a private attribute.
- **`StreamTurn` starts its turn before the first event**, so a second `StreamTurn` can never
  pass the busy check while the first is suspended. A client that drops before the turn's first
  event cancels that turn.
- **`WatchConversation` on an unknown conversation is `NOT_FOUND`**: a conversation starts with
  its first `StreamTurn`, as the hub's docstring says. The UI opens its watch after that turn.
  Recorded for the chat UI node (n9), which must not watch before the first turn.
- **Watch streams carry job-event turns only**; a `StreamTurn` consumer gets its own turn's
  events. A job-event turn's first event is its `job_update`.
- **Connect responses get CORS through the response context** (`ctx.response_headers`), added
  per handler to the UI-facing `ChatService`, `AgentJobs` and `SurveyTools` handler maps only.
  The tool bindings keep the bare handlers, which have no request context.
- **A failed call maps to `FAILED`, and a call cut short by cancel emits no `tool_call_finished`**:
  the turn ends as `turn_finished(CANCELLED)`, so `CANCELLED` is never a call status here.
- **`ToolCallFinished.result_json` and `JobResult.result_json` are empty** until the call or job
  succeeds (a detached call carries its `job` handle instead).
- **`CancelJob` waits up to 1 s for the cancelled job to settle** before it reports the job's
  state; `WaitForJobs` refuses a `timeout_s` above 300.
- **`ListModels` lists the models in a worker thread**, because the Ollama listing makes a
  blocking HTTP call.
- **Entry point refuses a real SAM**: `build_demo_workspace` needs `--sam-fake`, since the agent
  CLI has no SAM device or model flags yet. A real detector needs those flags first.
- **Demo host and stores**: the run host is built with `with_rtabmap=False`, as n7's test rig
  builds it; object GLBs are stored under `<cache-dir>/agent-geometry`.
