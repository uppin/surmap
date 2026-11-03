# Changeset: Survey agent — tool and chat protos with generated tool contracts

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — new proto package and codegen script, descriptor → JSON Schema generator, three service modules; one package

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (commit 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: `proto/surmap/agent/v1/{execution,survey_tools,jobs,chat}.proto` compile; `scripts/gen_agent_rpc.py` writes `_pb2.py`, `.pyi` and `agent_descriptor_set.binpb`
  - [ ] Milestone 2: `surmap.agent.contracts` builds one `ToolContract` per tool rpc from the descriptor set (name, description, schema, default execution)
  - [ ] Milestone 3: `surmap.agent.services` mounts `SurveyTools`, `AgentJobs`, `ChatService` with `UNIMPLEMENTED` handlers
  - [ ] Acceptance: `tests/test_agent_contracts.py` and `tests/test_agent_services.py` pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/agent.md` — create: tool catalogue table (tool, rpc, default execution) and the `execution` argument
  - [ ] `docs/connectrpc.md` — add `surmap.agent.v1` to the proto packages and its codegen command
  - [ ] `docs/surmap/changelog/2026-11-03-agent-tool-protos.md` — write changelog entry
  - [ ] Validate tests (`/validate-tests`)

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-agent-tool-protos-initial-discovery.md](./2026-11-03-agent-tool-protos-initial-discovery.md).

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **1 of 9** · #pending
**Branch**: `pr-1-survey-agent` · **Base**: `origin/main`
**Successor**: `pr-2-survey-agent`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance and unit tests

Why the boundary falls here: the proto contract is the seam every other node codes against —
runtime (n4) binds its contracts, tool handlers (n7) implement its service, the chat server (n8)
serves it and the UI (n9) generates its client from it.

### Owned API surface

- `proto/surmap/agent/v1/execution.proto`, `survey_tools.proto`, `jobs.proto`, `chat.proto`
- `scripts/gen_agent_rpc.py`; generated `src/surmap/agent/proto/*`
- `surmap.agent.contracts`: `ToolContract`, `ExecutionPolicy` (domain dataclass), `ExecutionMode`,
  `OnTimeout`, `tool_contracts(service_descriptor) -> tuple[ToolContract, ...]`,
  `resolve_execution(contract, arguments) -> ExecutionPolicy`
- `surmap.agent.services`: `survey_tools_module(handlers)`, `agent_jobs_module(handlers)`,
  `chat_service_module(handlers)` — each `ServiceModule`, missing handlers answer `UNIMPLEMENTED`

### Green wave

**Wave:** 1 of 4
**Node:** n1
**Concurrent with:** n2, n3, n4, n5, n6
**Blocks:** n7 (implements `SurveyTools` / `AgentJobs` handlers on these messages), n8 (serves the
three modules and `ChatService` events); n4 and n9 need only the stubs at compile level (contract
types; generated TS client)

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9

### Greenable independently?

**yes** — it owns everything its tests drive.

### Trunk-merge safety

**When this PR merges alone:** additive only — new proto package, generated modules and a library
with no caller. `uv run pytest -q`, the demo (`scripts/demo.py`) and the mission demo are untouched.
**Local dev data:** no. **Production data:** none.

## Affected Packages

- **surmap** (`src/surmap`): new `surmap.agent` package (`contracts`, `services`, `proto`);
  `pyproject.toml` ruff per-file ignores for the generated files.

## Related Feature Documentation

- PRD: [PRD-2026-11-03-agent-tool-protos.md](./PRD-2026-11-03-agent-tool-protos.md)
- `docs/connectrpc.md` — serving stack this reuses

## Summary

Tools are a proto service. One codegen step compiles them; a contract builder reads the descriptor
set (with source info) and gives every tool rpc a model-facing contract. The chat service the
browser uses is defined in the same package.

## Background

Planned in the `#survey-agent` stack: a LangGraph agent on Muse (Meta Responses API) and local
Ollama with tools to run demos, prompt SAM, find SAM objects and their 3D reconstructions, and get
raw or cropped frames. Tool calls may run long, so each call carries an execution policy — sync or
async, a timeout and what happens after it (fail, or detach to async) — and the developer chose
*proto defaults with a per-call model override*.

## Scope

- The four protos and the codegen script
- `ToolContract` generation, `execution` argument injection and resolution
- Service modules with `UNIMPLEMENTED` handlers
- **Out of scope:** handler behaviour (n7), job runner (n4), serving process (n8), TS codegen (n6/n9)

## Technical Changes

### State A (Current)

`proto/surmap/survey/v1/survey.proto` and `proto/surmap/transport/v1/socket_rpc.proto` only; codegen
`scripts/gen_survey_rpc.py` (`grpcio-tools==1.73.1`, patches `.pyi` `Mapping` args); services as
`ServiceModule(descriptor, bricks)` (`rpc/description.py`) with `Brick(methods=…)`
(`rpc/compose.py`), coverage gaps a mount-time error. No tool schema exists anywhere.

### State B (Target)

```proto
// execution.proto
extend google.protobuf.MethodOptions { ExecutionPolicy default_execution = 51001; }
enum ExecutionMode { EXECUTION_MODE_UNSPECIFIED = 0; SYNC = 1; ASYNC = 2; }
enum OnTimeout { ON_TIMEOUT_UNSPECIFIED = 0; FAIL = 1; DETACH = 2; }
message ExecutionPolicy { ExecutionMode mode = 1; uint32 timeout_s = 2; OnTimeout on_timeout = 3; }
message JobHandle { string job_id = 1; string tool = 2; JobStatus status = 3; string detail = 4; }
```

```proto
// survey_tools.proto (abridged)
service SurveyTools {
  // Lists the demo scenes this station can run, with their default SAM prompt and whether
  // their data is prepared.
  rpc ListDemos(ListDemosRequest) returns (ListDemosResponse) {
    option (default_execution) = { mode: SYNC timeout_s: 10 on_timeout: FAIL };
  }
  // Runs a demo scene with a SAM prompt and returns when the run ends. Runs take minutes:
  // by default it detaches to a job after 30 s; follow it with wait_for_jobs.
  rpc RunDemo(RunDemoRequest) returns (RunDemoResponse) {
    option (default_execution) = { mode: SYNC timeout_s: 30 on_timeout: DETACH };
  }
  rpc GetRun(GetRunRequest) returns (GetRunResponse);
  rpc PromptSam(PromptSamRequest) returns (PromptSamResponse);           // SYNC 60 s DETACH
  rpc FindObjects(FindObjectsRequest) returns (FindObjectsResponse);     // SYNC 15 s FAIL
  rpc GetObject(GetObjectRequest) returns (GetObjectResponse);           // SYNC 10 s FAIL
  rpc GetObjectGeometry(GetObjectGeometryRequest) returns (GetObjectGeometryResponse);
  rpc GetFrame(GetFrameRequest) returns (GetFrameResponse);              // crop box or object id
}
```

Each response that can finish after a detach is an ordinary message; the runtime wraps it in a
`JobHandle` when it detaches. `ChatService.StreamTurn` streams `TurnEvent { oneof text_delta,
tool_call_started, tool_call_finished, job_update, steer_applied, turn_finished, error }`.

```python
@dataclass(frozen=True)
class ToolContract:
    name: str                      # "run_demo"
    service: str                   # "surmap.agent.v1.SurveyTools"
    method: str                    # "RunDemo"
    description: str               # rpc leading comment
    input_schema: Mapping[str, object]   # JSON Schema 2020-12, with optional "execution"
    default_execution: ExecutionPolicy
```

### Delta (What's Changing)

#### surmap

- `proto/surmap/agent/v1/*.proto` (new), `scripts/gen_agent_rpc.py` (new)
- `src/surmap/agent/__init__.py`, `contracts.py`, `services.py`, `proto/` (new)
- `pyproject.toml` — ruff per-file ignores for `src/surmap/agent/proto/*_pb2.py*`

## Verification

**Method:** V1 — fail→pass acceptance and unit tests
**Command:** `uv run pytest -q tests/test_agent_contracts.py tests/test_agent_services.py`
**Before:** red — the stubs raise `NotImplementedError`; the protos and generated modules exist
from commit 2 so collection succeeds
**After:** green; plus `uv run --with grpcio-tools==1.73.1 python scripts/gen_agent_rpc.py && git diff --exit-code src/surmap/agent/proto` clean

## Testing Plan

- Contracts: build contracts from the checked-in descriptor set; assert names, descriptions from
  comments, enum fields as string enums, required/optional, unknown field rejected
  (`additionalProperties: false`), the injected `execution` property, and `resolve_execution`
  falling back to `default_execution` and honouring a model override.
- Services: mount each module on `InMemoryHost`; an rpc with no handler answers `UNIMPLEMENTED`;
  a supplied handler is called with the decoded request.
- Fixtures: the real `surmap.agent.v1` descriptor set — no network, no model.

## Acceptance Tests

### surmap

- `tests/test_agent_contracts.py`
  - every `SurveyTools` and `AgentJobs` rpc has a contract named in snake_case
  - a contract's description is its rpc's leading comment
  - `run_demo`'s schema accepts `{dataset, prompt}` and rejects an unknown field
  - every schema has an optional `execution` object with `mode`, `timeout_s`, `on_timeout`
  - `resolve_execution` returns the rpc default when `execution` is absent and the override when present
- `tests/test_agent_services.py`
  - each of the three modules mounts on `InMemoryHost`
  - an rpc without a handler answers `UNIMPLEMENTED`

## Decisions & Trade-offs

- **Descriptions from leading comments, not a custom option.** Comments are what reviewers read;
  the descriptor set must be compiled with `--include_source_info`, so it is checked in next to
  the `_pb2` files.
- **Schemas are built at import time from the descriptor set** rather than generated into Python
  modules: one generator, fewer generated files to keep in sync. Revisit if import time matters.
- **`execution` is injected, not declared in each request message** — one definition, no rpc can
  forget it; the runtime strips it before decoding the request.
- **Images in responses** (`GetFrame`) are `bytes` + `media_type`; the runtime turns them into model
  image content (n4/n7), not base64 in the JSON result.
