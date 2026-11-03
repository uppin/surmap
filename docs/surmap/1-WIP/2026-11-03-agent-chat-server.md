# Changeset: Survey agent chat server — `python -m surmap.agent`

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — server-streaming RPC with concurrent steer/cancel, wiring of four predecessors, socket e2e test

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (commit 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: `ChatHub` — conversations, one `AgentSession` each, event fan-out to `StreamTurn` / `WatchConversation` subscribers
  - [ ] Milestone 2: `ChatService` handlers (`StreamTurn`, `WatchConversation`, `Steer`, `CancelTurn`, `ListModels`, `GetConversation`) and runtime-event → `TurnEvent` mapping
  - [ ] Milestone 3: tool binding — `SurveyTools` handlers (n7) + job tools (n4) as agent tools; images as model image parts
  - [ ] Milestone 4: HTTP routes (`/geometry`, `/frames`, `/health`), CORS
  - [ ] Milestone 5: `surmap.agent.__main__` (flags, env, system prompt) on `HypercornHost`
  - [ ] Acceptance: `tests/test_agent_chat_service.py`, `tests/test_agent_server_e2e.py` pass
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

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **8 of 9** · #pending
**Branch**: `pr-8-survey-agent` · **Base**: `pr-7-survey-agent`
**Successor**: `pr-9-survey-agent`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance and unit tests

Why the boundary falls here: this is the composition root — the only node that wires protos (n1),
runtime (n4), models (n5) and tools (n7) into a process. Each of those is tested alone; this node
tests them together over Connect.

### Owned API surface

- `surmap.agent.server.hub`: `ChatHub`, `Conversation`
- `surmap.agent.server.chat_service`: `chat_handlers(hub)`, `turn_event_to_proto(event)`
- `surmap.agent.server.binding`: `agent_tools(contracts, handlers, runner)`
- `surmap.agent.server.routes`: `agent_http_routes(workspace)`
- `surmap.agent.server.app`: `build_agent_description(config)`, `AgentServerConfig`
- `surmap.agent.__main__`

### Green wave

**Wave:** 3 of 4
**Node:** n8
**Concurrent with:** none — this node is alone in its wave
**Blocks:** n9 (the UI talks to this server)

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9

### Greenable independently?

**no — blocked by n1, n4, n5 and n7**: the service tests stream real `AgentSession` turns (n4) over
mounted modules (n1), list models from the registry (n5) and call real tool handlers (n7). Tests red
for those stubs are blocked, not failures.

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

**Greenable independently?** no — needs n1, n4, n5, n7 green first.

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
**Before:** red — handlers raise `NotImplementedError` (blocked on n1/n4/n5/n7 until they green)
**After:** green with a scripted model; a live run is recorded at wrap: `uv run python -m surmap.agent --sam-fake --model ollama:<m>` answering "what demos can you run?" (or why it was not run)

## Testing Plan

- `InMemoryHost` client: `server_stream("StreamTurn", …)`, concurrent `unary("Steer", …)` and `unary("CancelTurn", …)`.
- `ScriptedChatModel` (n4's fake) injected through `AgentServerConfig.model_factory`.
- Socket e2e: `HypercornHost` on port 0, `/health`, one `StreamTurn` over HTTP/1.1 Connect.

## Acceptance Tests

### surmap

- `tests/test_agent_chat_service.py` — tool start/finish/text/finished sequence; steer during blocking `run_demo` (detach + reply); idle job-event turn on `WatchConversation`; cancel; `ListModels`; `GetConversation` replays history
- `tests/test_agent_server_e2e.py` — real socket: `/health`, one streamed turn, GLB and frame routes

## Decisions & Trade-offs

- **`WatchConversation` stream for idle events**: a server cannot push without an open stream; the
  UI keeps one per open conversation, and `StreamTurn` covers the turn it starts.
- **In-memory conversations**: survey sessions are short; durable storage is a follow-up TODO.
- **No auth; binds 127.0.0.1 by default** — the tools can start runs, so exposing it needs a deliberate `--host`.
