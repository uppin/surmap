# Survey agent — chat server - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Survey agent (new, `docs/agent.md` created at wrap) — how to run the agent and talk to it
- **Related Feature**: [Connect RPC](../../connectrpc.md), [Deployment](../../deployment.md) — a new hypercorn process

## Summary

`python -m surmap.agent` starts a hypercorn server that serves `ChatService` (streamed turns,
steering, cancel, model list), `AgentJobs` and `SurveyTools` over Connect, plus plain HTTP routes for
GLB geometry and frame images the UI shows.

## Background

The developer chose a dedicated process (not the stdlib demo server, which has no Connect streaming
and is oversized). The agent reads the same demo cache and run history as the console.

## Proposed Changes

### What's Changing

- `ChatService.StreamTurn(StreamTurnRequest{conversation_id, model_id, text})` → stream of
  `TurnEvent`s mapped from the runtime's events; job-event turns started while idle are delivered to
  the conversation's open `StreamTurn` subscribers (a client keeps one `WatchConversation` stream
  open per conversation for idle events).
- `ChatService.Steer`, `CancelTurn`, `ListModels`, `GetConversation` (history replay for reloads).
- `AgentJobs` served from the session's runner; `SurveyTools` served for direct UI invocation.
- HTTP: `GET /geometry/<run>/<object>.glb`, `GET /frames/<run>/<frame>.jpg?crop=…`, `GET /health`.
- CORS for the Vite dev origin (`SURMAP_AGENT_CORS_ORIGINS`, default `http://localhost:5173`).
- Flags/env: `--host`, `--port` (default 8780), `--history-db`, `--cache-dir`, `--model`,
  `--sam-fake`; system prompt names the tools' behaviour (say a job started, never that it finished;
  name job ids; use `wait_for_jobs` when the next step needs the result).

### What's Staying the Same

- Demo console, mission demo, viewer; no change to their ports or routes.

## Impact Analysis

### Technical Impact

A new process; in-memory conversations (lost on restart).

### User Impact

`uv run python -m surmap.agent --sam-fake` plus the chat UI is the whole local setup.

## Implementation Plan

See the changeset `2026-11-03-agent-chat-server.md`.

## Acceptance Criteria

1. A `StreamTurn` with a scripted model that calls `list_demos` streams tool start, tool finish,
   text and `turn_finished`.
2. A `Steer` during a blocking `run_demo` streams `steer_applied`, a detached `job_update`, and the
   model's reply to the steer.
3. A detached job that ends while idle reaches the conversation's watch stream as a job-event turn.
4. `CancelTurn` ends the stream with `turn_finished(reason=cancelled)`.
5. The GLB route serves a file a glTF parser accepts; the frame route serves a JPEG.
6. The server starts on port 0 over a real socket and answers `/health`.

## References

### Affected Features (Complete List)

- Survey agent (new); Connect RPC; Deployment
