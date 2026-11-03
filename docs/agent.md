# Survey agent (`surmap.agent`)

A chat agent that runs the survey demos and inspects their results through
tools. The tools are a proto service: one codegen step compiles them, and a
contract builder turns every tool rpc into the contract a model binds —
name, description, JSON Schema arguments and default execution policy.

## Layout

| Path | What |
|---|---|
| `proto/surmap/agent/v1/execution.proto` | `default_execution` method option, `ExecutionPolicy`, `ExecutionMode`, `OnTimeout`, `JobHandle` |
| `proto/surmap/agent/v1/survey_tools.proto` | `SurveyTools` — demo, SAM, object and frame tools |
| `proto/surmap/agent/v1/jobs.proto` | `AgentJobs` — follow and cancel detached tool calls |
| `proto/surmap/agent/v1/chat.proto` | `ChatService` — the browser's chat API (`StreamTurn`, `WatchConversation`, `Steer`, `CancelTurn`, `ListModels`, `GetConversation`), streaming `TurnEvent`s |
| `src/surmap/agent/proto/` | Generated `_pb2.py` / `.pyi` and `agent_descriptor_set.binpb` (checked in) |
| `src/surmap/agent/contracts.py` | `ToolContract`, `tool_contracts(service)`, `resolve_execution(contract, arguments)` |
| `src/surmap/agent/services.py` | `survey_tools_module`, `agent_jobs_module`, `chat_service_module` — `ServiceModule`s where an rpc with no handler answers `UNIMPLEMENTED` |

## Tool catalogue

A tool's name is its rpc in snake_case; its description is the rpc's
leading comment, and argument descriptions are the field comments.

| Tool | RPC | Default execution |
|---|---|---|
| `list_demos` | `SurveyTools.ListDemos` | SYNC · 10 s · FAIL |
| `run_demo` | `SurveyTools.RunDemo` | SYNC · 30 s · DETACH |
| `get_run` | `SurveyTools.GetRun` | SYNC · 10 s · FAIL |
| `prompt_sam` | `SurveyTools.PromptSam` | SYNC · 60 s · DETACH |
| `find_objects` | `SurveyTools.FindObjects` | SYNC · 15 s · FAIL |
| `get_object` | `SurveyTools.GetObject` | SYNC · 10 s · FAIL |
| `get_object_geometry` | `SurveyTools.GetObjectGeometry` | SYNC · 15 s · FAIL |
| `get_frame` | `SurveyTools.GetFrame` | SYNC · 15 s · FAIL |
| `wait_for_jobs` | `AgentJobs.WaitForJobs` | SYNC · 300 s · FAIL |
| `get_job` | `AgentJobs.GetJob` | SYNC · 10 s · FAIL |
| `cancel_job` | `AgentJobs.CancelJob` | SYNC · 10 s · FAIL |
| `list_jobs` | `AgentJobs.ListJobs` | SYNC · 10 s · FAIL |

Every tool rpc must declare `option (default_execution)`;
`tool_contracts` refuses a service with an rpc that does not.

Schema rules: a singular field without presence is `required`; `optional`
fields, oneof members, messages and repeated fields are not; every object
has `additionalProperties: false`; enums are string enums without their
`*_UNSPECIFIED` value; 64-bit integers are JSON `integer`.

## The `execution` argument

Every tool schema gets one optional argument, `execution`, injected by the
contract builder rather than declared in each request message:

```json
{"execution": {"mode": "ASYNC", "timeout_s": 120, "on_timeout": "DETACH"}}
```

- `mode` — `SYNC` blocks the turn; `ASYNC` returns a `JobHandle` at once.
- `timeout_s` — how long a `SYNC` call may run.
- `on_timeout` — `FAIL` the call, or `DETACH` it to a job the model follows
  with `wait_for_jobs`.

`resolve_execution(contract, arguments)` returns the rpc's
`default_execution` with any field the model gave overriding it; an
invalid value is a `ValueError`. The runtime strips `execution` before
decoding the request.

## Regenerating the bindings

```bash
uv run --with grpcio-tools==1.73.1 python scripts/gen_agent_rpc.py
git diff --exit-code src/surmap/agent/proto
```

The descriptor set is compiled with source info (the comments are the
descriptions). The script fixes the `.pyi` stubs for mypy strict: typed
`Mapping` arguments, module-level extension field numbers, and the
`default_execution` extension typed as the handle `HasExtension` takes.
