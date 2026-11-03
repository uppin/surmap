# Survey agent — tool and chat protos - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Survey agent (new, `docs/agent.md` created at wrap) — the proto contract every
  agent tool and the chat service are defined by
- **Related Feature**: [Connect RPC](../../connectrpc.md) — a third proto package served by the same
  `ServiceModule` + `Brick` stack

## Summary

Define the survey agent's tools as proto services and generate, from the proto descriptors, the
tool contracts an LLM binds: tool name, description, JSON schema of the arguments and the default
execution policy. Define the chat service the browser talks to.

## Background

The agent (later nodes of `#survey-agent`) needs tools whose schemas are reviewed as an API, served
over the same Connect stack as the rest of SurMap, and readable by a model. Writing schemas by hand
next to handlers drifts; deriving them from proto keeps one source.

## Proposed Changes

### What's Changing

- `proto/surmap/agent/v1/`:
  - `execution.proto` — `ExecutionMode {SYNC, ASYNC}`, `OnTimeout {FAIL, DETACH}`,
    `ExecutionPolicy {mode, timeout_s, on_timeout}`, `JobHandle`, `JobStatus`, and the method
    option `default_execution` every tool rpc declares.
  - `survey_tools.proto` — service `SurveyTools`: `ListDemos`, `RunDemo`, `GetRun`, `PromptSam`,
    `FindObjects`, `GetObject`, `GetObjectGeometry`, `GetFrame`.
  - `jobs.proto` — service `AgentJobs`: `WaitForJobs`, `GetJob`, `CancelJob`, `ListJobs`.
  - `chat.proto` — service `ChatService`: `StreamTurn` (server streaming `TurnEvent`), `Steer`,
    `CancelTurn`, `ListModels`.
- `scripts/gen_agent_rpc.py` — compiles the package (`_pb2.py`, `.pyi`) and writes a descriptor
  set with source info.
- `surmap.agent.contracts` — `ToolContract` per tool rpc: snake_case name, description from the
  rpc's leading comment, JSON Schema 2020-12 of the request (field comments → descriptions, enums
  as string enums), the default `ExecutionPolicy`, and an optional `execution` argument added to
  every tool so the model can override mode, timeout and post-timeout policy per call.
- `surmap.agent.services` — `ServiceModule`s for the three services whose handlers answer
  `UNIMPLEMENTED` until later nodes supply them.

### What's Staying the Same

- Existing `surmap.survey.v1` and `surmap.transport.v1` protos and their codegen.
- No runtime behaviour of any existing server.

## Impact Analysis

### Technical Impact

New generated files under `src/surmap/agent/proto/` (ruff-excluded like the survey ones). No new
runtime dependency.

### User Impact

None until the chat server node; this node ships the contract.

## Implementation Plan

See the changeset `2026-11-03-agent-tool-protos.md`.

## Acceptance Criteria

1. Every `SurveyTools` and `AgentJobs` rpc yields a `ToolContract` whose description is the rpc's
   leading comment and whose schema validates a well-formed request and rejects an unknown field.
2. Every contract's schema carries an optional `execution` object; omitting it resolves to the
   rpc's declared `default_execution`.
3. The three services mount on `InMemoryHost`, and an unimplemented call answers `UNIMPLEMENTED`.
4. Regenerating with `scripts/gen_agent_rpc.py` produces no diff.

## References

### Affected Features (Complete List)

- Survey agent (new)
- Connect RPC (`docs/connectrpc.md`)

### Related Documentation

- `docs/architecture.md` §1 (scope: passive survey only)
