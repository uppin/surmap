# Changeset: Survey agent runtime — LangGraph loop, job runner, steering

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — concurrency and ordering semantics (timeouts, detach, steering while calls block), new framework dependency under mypy strict, design choices recorded as settled-by-planner

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (commit 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: `langgraph`, `langchain-core` added to `pyproject.toml` / `uv.lock`; mypy strict clean
  - [ ] Milestone 2: `JobRunner` — policy resolution, sync wait with timeout, FAIL/DETACH, ASYNC, cancel, notices
  - [ ] Milestone 3: graph — model/tools/cut_off nodes, pending-message drain, round and repeated-failure caps
  - [ ] Milestone 4: `AgentSession` — `run_turn` event stream, `steer`, `cancel`, idle job-event signal
  - [ ] Milestone 5: built-in job tools (`wait_for_jobs`, `get_job`, `cancel_job`, `list_jobs`)
  - [ ] Acceptance: `tests/test_agent_runtime.py`, `tests/test_agent_jobs.py`, `tests/test_agent_steering.py` pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/agent.md` — add "Runtime" section: graph, execution policy table, job notices, steering, caps and env vars
  - [ ] `docs/surmap/changelog/2026-11-03-agent-runtime.md` — write changelog entry
  - [ ] Validate tests (`/validate-tests`)
  - [ ] (optional) Production readiness validated — run if the job runner keeps tasks past a cancelled turn

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-agent-runtime-initial-discovery.md](./2026-11-03-agent-runtime-initial-discovery.md).

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **4 of 9** · #pending
**Branch**: `pr-4-survey-agent` · **Base**: `pr-3-survey-agent`
**Successor**: `pr-5-survey-agent`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance and unit tests

Why the boundary falls here: the loop, the job semantics and steering are independent of which model
answers and which tools exist — tests drive them with a scripted model and fake tools. Providers (n5)
and real tools (n7) plug in through the `BaseChatModel` and `ToolContract` + handler seams.

### Owned API surface

- `surmap.agent.runtime.jobs`: `JobRunner`, `Job`, `JobState`, `JobNotice`, `ToolOutcome`
  (`Completed | Detached | Failed`)
- `surmap.agent.runtime.graph`: `build_turn_graph(model, tools, pending, caps)`, `TurnCaps`
- `surmap.agent.runtime.session`: `AgentSession` (`run_turn`, `steer`, `cancel`, `idle_events`),
  `ConversationStore` protocol + `InMemoryConversationStore`
- `surmap.agent.runtime.events`: `TextDelta`, `ToolCallStarted`, `ToolCallFinished`, `JobUpdate`,
  `SteerApplied`, `TurnFinished`, `TurnError`
- `surmap.agent.runtime.tools`: `bind_contract_tool(contract, handler, runner)`, `job_tools(runner)`
- `tests/agent_fakes.py`: `ScriptedChatModel`, `FakeToolHandler` (with hold/release for timing)

### Green wave

**Wave:** 1 of 4
**Node:** n4
**Concurrent with:** n1, n2, n3, n5, n6
**Blocks:** n8 (the chat server runs `AgentSession` turns and maps its events)

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9

### Greenable independently?

**yes** — its tests construct `ToolContract`s directly (n1's dataclass, a stub during this green is
not needed: the dataclass and `ExecutionPolicy` are plain types n1 publishes in its red commit) and
drive them with fake handlers and a scripted model.

### Trunk-merge safety

**When this PR merges alone:** additive package plus two dependencies; `uv run pytest -q` and every
demo unchanged. **Local dev data:** no. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `surmap.agent.contracts.ToolContract`, `ExecutionPolicy`, `ExecutionMode`, `OnTimeout`, `resolve_execution` | n1 | types real from n1's red commit; `resolve_execution` stub until n1 greens | uses the types; calls `resolve_execution` through an injected resolver so tests pass a local resolver instead of n1's stub |

**Greenable independently?** yes.

## Inherited Restructure — expect rewrite

n2 moves the demo run engine; this node touches no demo file. No fallout expected.

## Affected Packages

- **surmap** (`src/surmap/agent/runtime`), `pyproject.toml`, `uv.lock`.

## Related Feature Documentation

- PRD: [PRD-2026-11-03-agent-runtime.md](./PRD-2026-11-03-agent-runtime.md)

## Summary

The agent loop as a LangGraph `StateGraph` compiled per turn, with every tool call owned by a
`JobRunner`. The runner is what makes timeouts, detaching, async calls, steering and job notices one
mechanism: a tool call is always a job; "sync" only means the tool node waits for it.

## Background

See the PRD and Exploration 3 of the discovery companion (patterns adopted, and the two this stack
adds: per-call timeout with post-timeout policy, and steering).

## Scope

- Job runner, graph, session, events, job tools, scripted fake model
- **Out of scope:** model providers (n5), SurMap tools (n7), serving and persistence (n8), UI (n9)

## Technical Changes

### State A (Current)

No agent code; no LangChain/LangGraph dependency. Async tests run with `asyncio_mode = "auto"`.

### State B (Target)

```text
          ┌──────── pending (steers, job notices) drained here
START ─► model ──(tool calls)──► tools ──► model … ──(no calls)──► END
            └─(round cap | 3 identical failures)──► cut_off ──► END
```

```python
class JobRunner:
    async def call(self, contract: ToolContract, args: Mapping[str, object],
                   handler: Handler, *, policy: ExecutionPolicy) -> ToolOutcome: ...
    def detach_blocking(self, reason: str) -> int: ...       # every waiting SYNC call → Detached
    async def wait(self, ids: Sequence[str], mode: Literal["all", "any"], timeout_s: float) -> ...
    def cancel(self, job_id: str) -> bool: ...
    notices: asyncio.Queue[JobNotice]

class AgentSession:
    def run_turn(self, text: str | None, *, trigger: Literal["user", "job_event"]) -> AsyncIterator[TurnEvent]: ...
    def steer(self, text: str) -> SteerOutcome: ...           # queued | started_turn
    async def cancel(self) -> None: ...
    def idle_events(self) -> AsyncIterator[JobNotice]: ...    # notices that arrive while idle
```

A sync wait is `asyncio.wait({task, detach_event}, timeout=…)`: whichever fires first decides
Completed, Detached (steer or DETACH timeout) or Failed (FAIL timeout → task cancelled).

### Delta (What's Changing)

#### surmap

- `src/surmap/agent/runtime/{__init__,jobs,graph,session,events,tools}.py` (new)
- `tests/agent_fakes.py` (new)
- `pyproject.toml`, `uv.lock` — `langgraph>=1.2,<2`, `langchain-core>=1.6,<2`

## Verification

**Method:** V1 — fail→pass acceptance and unit tests
**Command:** `uv run pytest -q tests/test_agent_runtime.py tests/test_agent_jobs.py tests/test_agent_steering.py`
**Before:** red — stubs raise `NotImplementedError`
**After:** green, deterministic (no sleeps: fake handlers block on events the test releases; timeouts are 0.05 s)

## Testing Plan

- `ScriptedChatModel(BaseChatModel)`: returns scripted `AIMessage`s in order, repeats the last,
  records every history it saw and the tools bound.
- `FakeToolHandler`: completes, fails, or holds until released; records calls.
- Real graph, real runner, real in-memory store.

## Acceptance Tests

### surmap

- `tests/test_agent_runtime.py`
  - a model answering without tools finishes with reason `stop` and streams text deltas
  - a tool result is fed back and the model's next history ends with the tool message
  - the round cap routes to `cut_off` with "Not run" results; three identical failures do too
  - a failing handler becomes a failed tool result, not a turn error
- `tests/test_agent_jobs.py`
  - sync within timeout → inline result
  - sync past timeout + DETACH → handle; notice delivered before the next model call
  - sync past timeout + FAIL → cancelled, failed result naming the timeout
  - `execution: {mode: ASYNC}` → handle at once; `wait_for_jobs` returns its result
  - a job ending while idle is emitted by `idle_events`
- `tests/test_agent_steering.py`
  - steer during a blocking call detaches it (`detached by steer`) and the steer is the last human message the model sees next
  - steer while idle starts a turn
  - cancel ends the turn and cancels running jobs; completed rounds stay in history

## Decisions & Trade-offs

- **Every call is a job.** One mechanism for sync, async, detach and steering; "sync" is the tool
  node waiting on the job. Costs a job id for trivial calls; they are cheap.
- **Pending messages drain before the model node, not via LangGraph `interrupt`.** `interrupt`
  pauses for input; steering must not pause — it adds input and keeps running.
- **No checkpointer**: history comes from the conversation store and is appended round by round, so
  there is one copy of history.
- **Steer detaches, never cancels**: the person may still want the result; the model can cancel it.
- **Round cap 30** (not 50): SurMap tools are coarse; 30 rounds is far past a sane survey question.
- **Complexity 5** is a warning the boundary may be wide; it holds because the three mechanisms share
  the runner — splitting them would test the runner twice through two half-graphs.
