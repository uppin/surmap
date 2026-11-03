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

## Tools (`surmap.agent.tools`)

`survey_tool_handlers(workspace)` maps every `SurveyTools` rpc to a handler over a
`SurveyWorkspace` port (`tools/port.py`). `DemoWorkspace` (`tools/workspace.py`) is the default
adapter: it drives the demo's `DemoRunHost` headlessly, reads its run history (so agent runs show
in the console) and publishes GLB through a `GeometryStore` (`tools/geometry.py`). Read/run only.

| Tool | Arguments | Result | Default execution |
|---|---|---|---|
| `list_demos` | — | every scene: `id`, `title`, `default_prompt`, `prepared`, `cached_run_id` | SYNC · 10 s · FAIL |
| `run_demo` | `dataset`; `prompt` (scene default); `max_frames` (whole scene); `fps` (native, > 0) | the ended run: `run_id`, frames, objects, `status` | SYNC · 30 s · DETACH |
| `get_run` | `run_id` | `RunInfo`: dataset, prompt, frames, objects, status | SYNC · 10 s · FAIL |
| `prompt_sam` | `run_id`, `concept`; `frame_ids` or `max_frames` (≤ 8) | per frame: `frame_id`, `t_ns`, detections with ids, label, score, box, mask polygon | SYNC · 60 s · DETACH |
| `find_objects` | `run_id`; `label`, `near` + `radius_m`, `moving`, `limit` | object summaries, nearest first with `near`, else largest first; no neighbours | SYNC · 15 s · FAIL |
| `get_object` | `run_id`, `object_id` | one summary with its nearest neighbours (5 m, 5 nearest) | SYNC · 10 s · FAIL |
| `get_object_geometry` | `run_id`, `object_id`; `max_points` (500), `voxel_m` | `surmap-obj v1` text and the GLB `geometry_uri` | SYNC · 15 s · FAIL |
| `get_frame` | `run_id`; `frame_index` / `frame_id` / `t_ns` (first frame); `crop_box` / `crop_object_id`; `pad_px`; `max_side` | one JPEG as image content, its size and `source` (`FULL` / `DISPLAY`) | SYNC · 15 s · FAIL |

- **Objects.** An object's id is `obj_<surface_id>` of the run history's surface; its points are
  every point the run assigned to it, in frame `map`, up axis `-y`. `status` maps the history:
  `running` → `RUNNING`, `completed` → `FINISHED`, `interrupted` → `CANCELLED`, else `FAILED`.
- **Geometry URIs.** `surmap-glb://<run_id>/<object_id>.glb`, written once per object; both parts
  must match `[A-Za-z0-9_-]+`, so a URI never names a path outside the store.
- **Frames and crops.** `get_frame` reads the full-resolution scene frame when cached, else the
  run's display JPEG; `prompt_sam` runs on the same image, so its boxes and crops share one pixel
  space. `crop_object_id` crops to the object's recorded SAM mask box, scaled to the image and
  padded 16 px unless `pad_px` is given; with no frame chosen it takes the object's first frame
  with a box. Crops are clamped to the frame, then downscaled to `max_side`.
- **Cancel.** Cancelling `run_demo` stops the run it started, including one still starting.
- **Errors.** `NOT_FOUND` — unknown scene, run, frame or object, or an object with no mask box on
  the frame; `INVALID_ARGUMENT` — `near` without `radius_m`, non-positive `fps`, `max_frames` 0,
  a crop outside the image; `UNAVAILABLE` — the previous run did not stop in time.

## Regenerating the bindings

```bash
uv run --with grpcio-tools==1.73.1 python scripts/gen_agent_rpc.py
git diff --exit-code src/surmap/agent/proto
```

The descriptor set is compiled with source info (the comments are the
descriptions). The script fixes the `.pyi` stubs for mypy strict: typed
`Mapping` arguments, module-level extension field numbers, and the
`default_execution` extension typed as the handle `HasExtension` takes.

## Runtime (`surmap.agent.runtime`)

The agent loop: a LangGraph `StateGraph` compiled per turn, with every tool call run as a job by
a `JobRunner`. "Sync" only means the tool node waits for the job, so timeouts, detaching, async
calls, steering and job notices are one mechanism.

| Module | What |
|---|---|
| `jobs.py` | `JobRunner` (`call`, `detach_blocking`, `wait`, `get`, `jobs`, `cancel`, `cancel_all`, `notices`), `Job`, `JobState`, `JobNotice`, `JobWait`, `ToolOutcome` (`Completed \| Detached \| Failed`) |
| `graph.py` | `build_turn_graph(model, tools, pending, caps)`, `TurnCaps` (`from_env`), `TurnState`, `turn_input` |
| `session.py` | `AgentSession` (`run_turn`, `steer`, `cancel`, `idle_events`), `ConversationStore`, `InMemoryConversationStore` |
| `events.py` | `TextDelta`, `ToolCallStarted`, `ToolCallFinished`, `JobUpdate`, `SteerApplied`, `TurnFinished`, `TurnError` |
| `tools.py` | `BoundTool`, `bind_contract_tool(contract, handler, runner)`, `job_tools(runner, contracts)` |

### Graph

```text
          ┌──────── pending (job notices, then steers) drained here
START ─► model ──(tool calls)──► tools ──► model … ──(no calls)──► done ──► END
            └─(round cap | repeated identical failures)──► cut_off ──► END
```

- `model` drains the pending messages, appends them to the state, and streams one model call
  (text arrives as `TextDelta`s).
- `tools` runs the calls of one model reply one at a time through their `BoundTool`; an unknown
  tool, invalid arguments or a failing handler becomes a failed tool result, never a turn error.
- `cut_off` answers every unanswered call with a "Not run" tool result and ends the turn with
  `round_cap` or `repeated_failure`.
- There is no checkpointer: the session seeds the graph with the stored history and appends what
  each round adds, so one copy of history exists and a stopped turn keeps its completed rounds.
- `TurnFinished(reason)` is always the last event; `reason` is `stop`, `round_cap`,
  `repeated_failure`, `cancelled` or `error` (an `error` follows a `TurnError`). When a turn stops
  with calls still unanswered, each gets a "Not run" tool result so the history stays valid.

### Execution policy

Each call's policy is the rpc's `default_execution` with the model's `execution` argument applied
(`resolve_execution`); the handler never sees `execution`. `JobRunner(timeout_scale=…)` sets how
many seconds one `timeout_s` unit lasts (1.0 in production).

| Mode | `on_timeout` | Finishes within `timeout_s` | Still running at `timeout_s` |
|---|---|---|---|
| `SYNC` | `FAIL` | result inline | job cancelled; failed result `timed out after <n>s` |
| `SYNC` | `DETACH` | result inline | job handle (`detached after the <n>s timeout`); the job keeps running |
| `ASYNC` | either | job handle at once (`async`) | — |

### Jobs and notices

- Every call is a job with id `j-1`, `j-2`, … in start order, a state (`RUNNING`, `SUCCEEDED`,
  `FAILED`, `CANCELLED`), its result or error, a `detail` and start/finish times.
- A detached call's tool result tells the model the job id and points it at `wait_for_jobs`,
  `get_job` and `cancel_job` (bound by `job_tools` over the `AgentJobs` contracts; `list_jobs`
  lists every job newest first). `wait_for_jobs` takes mode `ALL` or `ANY` and a timeout (default
  300 s).
- When a detached or async job ends (other than by cancel), a `JobNotice` — e.g.
  `Job j-3 run_demo succeeded: {...}` — is queued on `JobRunner.notices`. During a turn it is read
  before the next model call and reported as a `JobUpdate`; while no turn runs it comes out of
  `AgentSession.idle_events()`, for the chat server to start a `job_event` turn.

### Steering

- `AgentSession.steer(text)` during a turn queues the text as a pending human message and detaches
  every waiting `SYNC` call (`detail="detached by steer"`); it returns `SteerQueued(detached=n)`.
  The model reads the steer on its next call, after any queued notices, so the steer is the last
  human message it sees; the turn emits `SteerApplied` with the detached call ids.
- **A steer detaches, never cancels**: the person may still want the result, and the model can
  `cancel_job` it.
- On an idle session `steer` starts a normal turn and returns `TurnStarted(events)`.
- Steers and notices are human messages tagged in `additional_kwargs["surmap_kind"]` (`steer`,
  `job_notice`); the repeated-failure count restarts only at an untagged human message.
- Steering does not use LangGraph `interrupt`, which pauses for input; a steer adds input and the
  turn keeps running.

### Caps

| Cap | Default | Set by |
|---|---|---|
| Tool rounds per turn | 30 | `SURMAP_AGENT_MAX_ROUNDS` (positive integer; anything else is a `ValueError`), read by `TurnCaps.from_env` |
| Identical failing calls (same tool, same arguments) per turn | 3 | `TurnCaps(max_identical_failures=…)` |

### Cancel

- `AgentSession.cancel()` cancels every running job and the turn, which ends
  `TurnFinished("cancelled")`; completed rounds stay in the conversation. It waits up to 1 s for
  the jobs to end — a handler that ignores cancellation outlives it.
- A turn cancelled any other way (its event reader goes away) cancels the `SYNC` call it was
  waiting on with it; detached and async jobs keep running and report as notices.
- One turn runs per session at a time; `run_turn` on a busy session raises `RuntimeError`.

## Object 3D contract (`surmap.objects3d`)

How an agent sees a detected object's 3D reconstruction. A pure numpy library (no new
dependency, no caller until the object tools): an always-present summary, an on-request
text block the model can read, and a GLB for viewers. Points today; faces are an optional
argument every function already accepts.

| Module | What |
|---|---|
| `summary.py` | `ObjectSummary`, `summarize(...)`, `neighbours(...)` |
| `obj_text.py` | `encode_obj_text`, `decode_obj_text`, `ObjTextLimits`, `DecodedObj` |
| `glb.py` | `write_glb`, `read_glb_header`, `GlbHeader` |

### Summary fields

Field names match `surmap.agent.v1.ObjectSummary` one for one. Every coordinate is metres
in the stated `frame`; `up_axis` is `-y` for the demo's RTAB-Map map and `+z` for ENU
snapshots, and height and footprint are computed along it.

| Field | Meaning |
|---|---|
| `id`, `label`, `confidence` | identity; `confidence` may be `None` |
| `frame`, `up_axis`, `units` | the coordinate frame, its up axis (`+y`, `-y`, `+z`), always `m` |
| `n_points`, `n_faces` | geometry counts |
| `centroid`, `aabb_min`, `aabb_max` | mean point and axis-aligned box |
| `obb` | `centre`, `extents` (half-lengths along the box axes, largest first), `rotation` (row-major 3x3, column `i` is box axis `i`) |
| `height_m`, `footprint_m2` | extent along the up axis; area of the points' footprint on the plane perpendicular to it |
| `shape` | `linear`, `planar` or `volumetric` from PCA eigenvalue ratios |
| `observed_frames`, `t_first_ns`, `t_last_ns` | observation count and time span (the times may be `None`) |
| `neighbours` | `(id, distance_m, relation)` tuples; empty until `neighbours(...)` fills them in |
| `geometry_uri` | where the GLB lives, if published |

`confidence`, the times and `geometry_uri` differ from the proto only in that they are `None`-able
here where proto3 has plain scalars (`None` becomes `0` / `""`).

### `surmap-obj v1` text

```text
# surmap-obj v1 id=obj_17 label=car frame=map up=-y unit=cm
# origin_m=412.35,-88.10,2.04 scale=0.01 points=500 (decimated from 14211)
v -226 -90 -74 158 156 153
v -224 -90 -70 160 158 151
...
```

```text
# surmap-obj v1 id=tri label=roof frame=map up=+z unit=cm
# origin_m=3.00,2.00,0.50 scale=0.01 points=3
v -50 -50 0
v 50 -50 0
v 0 50 0
f 1 2 3
```

- Two comment lines open the block. Line 1: `id`, `label`, `frame`, `up` (`+y|-y|+z`), `unit=cm`;
  spaces inside a value become `_`. Line 2: `origin_m` (the OBB centre, metres),
  `scale=0.01` (metres per unit), `points=<kept>` and, when thinned, `(decimated from <N>)`.
- `v x y z [r g b]`: integer centimetres from `origin_m`, then optional 0-255 colour. Every
  vertex line carries colour or none does.
- `f a b c`: 1-based vertex indices, triangles only. Faces whose vertices were dropped are
  dropped.
- Limits (`ObjTextLimits`): voxel 5 cm, at most 500 points and 1,000 faces. Decimation is
  deterministic: the first point per voxel, then an even stride over the kept set, so the same
  cloud always gives the same text.
- `decode_obj_text` returns `DecodedObj` with points back in frame metres, faces 0-based, and
  `decimated_from`; anything that is not a v1 block raises `ValueError`.

### GLB layout

One mesh, one primitive. `POSITION` is float32 VEC3 in the object frame's metres, with
accessor `min`/`max` equal to the AABB. Mode 0 (`POINTS`) for a point set; mode 4
(`TRIANGLES`) with a uint32 `indices` accessor when faces are given. Optional `COLOR_0` is
normalised unsigned-byte VEC3. `asset.extras` carries `frame` and `up_axis`. `read_glb_header`
returns the magic, version, length, primitive modes, position bounds, extras and BIN length
for checking a file.

### Decided without review

- **Footprint is the convex hull** of the points projected onto the plane perpendicular to the
  up axis (monotone chain), so a rotated box reports its true footprint and collinear points
  report 0.
- **PCA shape thresholds**: a principal variance at or below 0.1 of the next larger one
  collapses that dimension: middle <= 0.1 x largest is `linear`, smallest <= 0.1 x middle is
  `planar`, otherwise `volumetric`.
- **Relations are measured from the summarised object**: distance is the gap between the two
  AABBs (0 when they touch). All gaps zero is `overlaps`; a gap only along the up axis is
  `above` or `below` by which way the other centroid sits; anything else is `next_to`.
  Defaults: 5 m search distance, 5 neighbours, nearest first.
- **Integer centimetres from the OBB centre**, not a normalised grid, so the agent reads real
  dimensions in three digits.
- **No `pygltflib`**: the writer is plain struct packing.

## Models (`surmap.agent.llm`)

The runtime binds a LangChain `BaseChatModel`. `ChatModelRegistry`
(`registry.py`) lists the models usable right now and builds one by id.

| Id | Provider | Listed when | Built as |
|---|---|---|---|
| `meta:<model>` | Meta Model API, Responses (`POST {base}/responses`) | `MODEL_API_KEY` is set; the model is `SURMAP_AGENT_META_MODEL`, else `muse-wonder-1.0` | `MetaResponsesChatModel` (`meta.py`) |
| `ollama:<model>` | Loopback Ollama (`SURMAP_OLLAMA_URL`, else the labelling default) | the server's `GET /api/tags` names it; an unreachable server lists nothing | `ChatOllama` via `ollama_chat_model` (`ollama.py`) |

An id splits at the first colon (`ollama:llama3.2:3b` is Ollama model
`llama3.2:3b`). `build` does not consult the listing: any `meta:` or
`ollama:` id builds; any other provider raises `UnknownModelProvider`.
The registry reads an injected `environ` (default `os.environ`).

### Muse on the Responses API

`MetaResponsesChatModel` defaults: model `muse-wonder-1.0`,
`reasoning_effort` `medium`, `max_output_tokens` `8192`. The key is
`MODEL_API_KEY` (or `api_key`), sent only as `Authorization: Bearer`;
a missing key raises `MetaResponsesError` before any request. The
transport is `labelling.meta_muse`'s, which refuses redirects. One
response is one chunk; there is no token streaming.

The mapping is two pure functions:

- `responses_request(messages, tools, *, model, effort, max_output_tokens)`:
  the system message becomes `instructions`; human text and images
  become `input_text` / `input_image` (data URL) parts; AI text is sent
  before its tool calls; each tool call is a `function_call` item
  (`call_id`, `name`, `arguments` as `json.dumps(args)`) and each tool
  result a `function_call_output` with the same `call_id`. Tools are
  `{type: "function", name, description, parameters, strict: false}`;
  no tools means no `tools` field, and `tool_choice` is refused.
- `parse_responses(body, *, requested_model)`: `output_text` parts are
  the content, `function_call` items the tool calls in order,
  unparseable arguments an invalid tool call, `usage` the message's
  usage metadata. A body with no `output` list is refused.

An empty reply (no text, no tool call) is asked for once more, then
raises `MetaResponsesError`. Every response with usage goes to
`usage_sink` (normally a `UsageLedger`, provider `meta`), and
`before_call` (normally `UsageLedger.check`) runs before every request,
so a spent `SURMAP_BUDGET_META_*` budget refuses the turn before a
socket opens.

### Live checks

| Check | Command | Result on the dev host |
|---|---|---|
| Muse tool round trip (`echo`) | `SURMAP_LIVE_META=1 uv run pytest -q tests/test_agent_llm_meta.py -k live` | **Not run — no `MODEL_API_KEY` on the dev host. Live Meta function-tool support is unverified**: the request and reply shapes follow the OpenAI-style Responses API and are pinned only by hand-built fixtures |
| Ollama tool round trip | `SURMAP_LIVE_OLLAMA=1 SURMAP_OLLAMA_MODEL=<model> uv run pytest -q tests/test_agent_llm_registry.py -k live` | Passed against `fastcontext-tools:latest` |

## Running the agent

`python -m surmap.agent` (`src/surmap/agent/__main__.py`) serves the
agent on hypercorn:

```bash
uv run python -m surmap.agent --sam-fake                          # Muse (meta:) default model
uv run python -m surmap.agent --sam-fake --model ollama:llama3.2  # a local Ollama model
```

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | bind address — loopback unless you say otherwise; the server has no auth |
| `--port` | `8780` | `0` picks a free port; the bound one is printed as `survey agent on http://…` |
| `--model` | `meta:<DEFAULT_AGENT_META_MODEL>` | default model id (`ListModels` lists the rest) |
| `--history-db` | demo default | demo run history DB |
| `--cache-dir` | demo default | demo scene cache; object GLBs go to `<cache-dir>/agent-geometry` |
| `--sam-fake` | off | fake centred-box SAM — **required for now** |

Environment: `SURMAP_AGENT_CORS_ORIGINS` — comma-separated browser
origins allowed by CORS (default `http://localhost:5173`, the chat UI's
Vite dev server; blank entries dropped). Model credentials and budgets
are the providers' own (`MODEL_API_KEY`, `SURMAP_BUDGET_META_*`, Ollama
on its default port — see *Models* above). Ctrl-C stops the host and
prints `survey agent stopped`.

**Served.** Connect services `surmap.agent.v1.ChatService`, `AgentJobs`
and `SurveyTools` (the UI may call a survey tool directly), plus HTTP:

| Route | Returns |
|---|---|
| `GET /health` | `ok` |
| `GET /geometry/<run_id>/<object_id>.glb` | an object's published GLB (`model/gltf-binary`), 404 when absent |
| `GET /frames/<run_id>/<frame_id>.jpg[?crop=x0,y0,x1,y1&max_side=N]` | a run frame, optionally cropped / downscaled; 400 on a malformed query |

CORS headers go only to allowed origins, on Connect responses and the
HTTP routes alike; `OPTIONS` answers the preflight.

**Event stream.** `StreamTurn` streams the turn's `TurnEvent`s, each
with `conversation_id`, `turn_id` and a per-conversation `seq`: first
`user_message`, then `text_delta`, `tool_call_started` /
`tool_call_finished` (with any tool `image`), `job_update`,
`steer_applied`, and last `turn_finished` (or `error`). A conversation
starts with its first `StreamTurn` (one `AgentSession` each, in the
`ChatHub`); a second `StreamTurn` while a turn runs is refused as busy.
`WatchConversation` streams the turns a finished job starts (each opens
with that job's `job_update`); `GetConversation` replays every event.
`Steer` on an idle conversation returns `accepted=false`; `CancelTurn`
ends the turn as `turn_finished(CANCELLED)`. `AgentJobs` requests name
their conversation in the `surmap-conversation-id` header.

**Limits.**

- **`--sam-fake` only.** Without it the process refuses to start: the
  CLI has no SAM device / model / route flags yet. Recorded:
  `src/surmap/docs/todo/2026-11-03-agent-cli-sam-flags.md`.
- **Tool images reach the model as a placeholder**
  (`<image/jpeg, N bytes, shown to the user>`); the stream carries the
  real bytes to the UI. Recorded:
  `src/surmap/docs/todo/2026-11-03-agent-tool-image-parts.md`.
- **`WatchConversation` before the first turn is `NOT_FOUND`** — open the
  watch after the conversation's first `StreamTurn`.
- Conversations live in memory for the process lifetime.

## Chat UI

`web/agent-chat/` is the browser client of `ChatService`
([web/agent-chat/README.md](../web/agent-chat/README.md)). With the agent
running on its default port:

```bash
uv run python -m surmap.agent --sam-fake --model ollama:llama3.2
cd web/agent-chat && yarn local-install && yarn dev   # http://localhost:5173
```

![Chat UI after one turn: a list_demos tool step with its policy and the reply](images/agent-chat.png)

- **Query parameters.** `?server=` names the agent server (default
  `http://127.0.0.1:8780`; its origin must be in
  `SURMAP_AGENT_CORS_ORIGINS`). `?conversation=` names the conversation;
  without it each tab keeps one id of its own in `sessionStorage`, so a
  reload keeps the conversation and redraws it from `GetConversation`.
- **Transcript.** User messages, streamed Markdown replies, and one card
  per tool call with its resolved execution policy (`SYNC 10 s → FAIL`,
  `SYNC 30 s → DETACH`, `ASYNC`), status (Running, Done, Failed,
  Detached, Cancelled), duration and expandable arguments.
- **Steering while busy.** The composer never locks. While a turn runs
  it offers **Steer** (sends `Steer`; the transcript shows
  `Steered: …`) and **Stop** (`CancelTurn`). A steer the server does not
  accept starts a new turn with the same text.
- **Jobs panel.** Detached and `ASYNC` calls appear as jobs with tool,
  status and elapsed time; **Cancel** on a running job calls
  `AgentJobs` with the conversation header. Turns a finished job starts
  arrive on the `WatchConversation` stream, opened once the server knows
  the conversation, and begin with a job notice.
- **Previews.** A tool image is drawn inline from its bytes; an object
  GLB from `/geometry/…` is drawn by a lazily loaded three.js preview
  (its core, renderer and loader chunks load only when a preview is
  shown).
- **Model picker.** Lists `ListModels`, preselects the server default,
  and sends the chosen id with each turn.
