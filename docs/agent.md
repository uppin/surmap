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
