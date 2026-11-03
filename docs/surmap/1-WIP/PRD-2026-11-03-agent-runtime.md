# Survey agent — LangGraph runtime with async tools and steering - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Survey agent (new, `docs/agent.md` created at wrap) — the agent loop, how
  long tool calls behave, and how a person steers a running turn

## Summary

A LangGraph agent loop whose every tool call runs as a job with an execution policy (sync or async,
timeout, fail or detach after the timeout), whose finished jobs come back into the conversation as
notices, and which a person can steer mid-turn by pushing a pending message — which moves any
blocking tool call to async so the model can read the message at once.

## Background

Agent tools here run demos and SAM, which take seconds to minutes. A blocking call freezes the
conversation; a fire-and-forget call loses the result. The developer asked for per-call timeouts with
a post-timeout policy, async execution, and steering.

## Proposed Changes

### What's Changing

- **Graph** per turn: `model → tools → model …`; END when the model asks for no tool; a round cap
  (default 30, `SURMAP_AGENT_MAX_ROUNDS`) and a repeated-identical-failure cap (3) route to a
  `cut_off` node that answers the unanswered calls with "Not run" tool results and closes the turn.
  Before each model call, pending messages (steers, job notices) are appended to the state.
- **Execution policy**, per call: the tool's proto default overridden by the model's optional
  `execution` argument. `SYNC`: wait up to `timeout_s`; on timeout `FAIL` cancels and reports a
  timeout error, `DETACH` returns a job handle and keeps the call running. `ASYNC`: return a handle
  at once.
- **Jobs**: `JobRunner` owns every call as an asyncio task with id, tool, status
  (`running | succeeded | failed | cancelled`), result or error, and timestamps. Built-in tools
  `wait_for_jobs` (ids, `all | any`, ceiling 300 s), `get_job`, `cancel_job`, `list_jobs`.
- **Job notices**: when a detached or async job ends, a system notice ("Job j-3 run_demo
  succeeded: …") is queued for the conversation. During a turn it is read before the next model
  call; when idle the session signals that a job-event turn should start (the server, n8, starts
  it).
- **Steering**: `AgentSession.steer(text)` queues a pending human message and detaches every
  in-flight blocking call (its waiting tool result becomes a job handle with
  `detail="detached by steer"`). The model sees the steer on its next call. Steering an idle session
  starts a normal turn.
- **Cancel**: cancels the turn and its in-flight jobs; completed rounds stay in history.
- **Events**: the turn yields domain events — `TextDelta`, `ToolCallStarted`, `ToolCallFinished`
  (result or handle), `JobUpdate`, `SteerApplied`, `TurnFinished(reason)`, `TurnError` — which the
  chat server maps onto `ChatService.TurnEvent`.

### What's Staying the Same

- No existing module changes; no server or UI here.

## Impact Analysis

### Technical Impact

New dependencies `langgraph` and `langchain-core` (typed). Runtime is in-process asyncio; no
persistence beyond an in-memory conversation store.

### User Impact

None until the chat server and UI land.

## Implementation Plan

See the changeset `2026-11-03-agent-runtime.md`.

## Acceptance Criteria

1. A scripted model that answers without tools ends the turn with `TurnFinished("stop")`.
2. A sync call that finishes within its timeout returns its result inline.
3. A sync call past its timeout with `DETACH` returns a job handle; its later result arrives as a
   notice before the model's next call (in-turn) or raises the job-event signal (idle).
4. A sync call past its timeout with `FAIL` is cancelled and reported as a failed tool result.
5. `execution: {mode: ASYNC}` returns a handle immediately.
6. Steering while a blocking call runs detaches it, and the steer text is the last human message the
   model sees on its next call.
7. A model that keeps calling tools stops at the round cap via `cut_off`; three identical failing
   calls stop via `cut_off`.
8. Cancel ends the turn and cancels running jobs.

## References

### Affected Features (Complete List)

- Survey agent (new)
