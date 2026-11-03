# Initial Discovery — agent runtime (n4 of #survey-agent)

Exploration 1 below is the whole-work pass for the stack, copied verbatim.

## Combined Conclusions (this node)

- No LangGraph/LangChain dependency yet; tests run asyncio auto mode.
- Patterns to keep and the two additions (timeout policy, steering): Exploration 3.

## Exploration 1 (whole work) — combined conclusions

- **No agent code exists.** Nothing in `src`, `pyproject.toml` or `uv.lock` references LangChain or
  LangGraph. Every model call today is one request with at most one retry
  (`mapqa/client.py:108`, `labelling/baseten_muse.py:225`, `evaluation/ladi.py:443`). Tool calling is
  used only for structured output (`record_label`, `record_classes`); no result is ever fed back to
  a model.
- **Muse runs on the Meta Responses API** (`POST https://api.meta.ai/v1/responses`, Bearer
  `MODEL_API_KEY`, `reasoning.effort`, `max_output_tokens`, `text.format` JSON schema,
  `input_image` data URLs — `labelling/meta_muse.py:1-28`, `mapqa/client.py:79-150`). Function-tool
  support on that endpoint is **unverified** — no SurMap code sends `tools` to it. The developer
  chose this route only (no Baseten for the agent), so the live tool-call check is the first
  acceptance gate of the providers node.
- **Ollama** is reached on loopback `/api/chat` (`labelling/ollama.py:27-133`,
  `SURMAP_OLLAMA_URL`, `SURMAP_OLLAMA_MODEL`), no key.
- **RPC stack to reuse:** `connectrpc==0.12.1` on hypercorn, protos compiled by `grpcio-tools`
  (`scripts/gen_survey_rpc.py`, generated `_pb2.py` + `.pyi` checked in and excluded from ruff).
  Services are `ServiceModule(descriptor, bricks)` + `Brick(methods=…)`
  (`rpc/description.py`, `rpc/compose.py`), hosted by `HypercornHost`, tested in process with
  `InMemoryHost(desc, ctx).client(descriptor).unary/server_stream(...)`. Clients in SurMap are
  hand-rolled (`demo/remote.py:75-90`).
- **Demo runs start only through SSE `GET /stream`** (`demo/server.py:1326` `start_run`, `:1396`
  `_take_over`, `:1680` `_RunEngine`). `demo/server.py` is 2,215 lines and has an open
  `oversized-file-demo-server` code issue (`src/surmap/docs/code-issues/`). A headless start needs
  the run engine outside that file.
- **SAM prompt is per run** (`demo/sam_prompt.py:19-30`): re-prompting means a new run, or
  re-answering a mask polygon offline against a recorded run's dense buffer
  (`slam/dense.py:389 dense_region_points`).
- **Objects are point sets only:** `Surface(surface_id, label, points: NDArray[float32] Nx3, moving)`
  (`survey/surfaces.py:91`), queried per run via `RunHistoryStore.surfaces_at(run_id, frame_id)`.
  No mesh code exists. The demo's live map frame is RTAB-Map y-down (`cloud_view.py:6-8`); the
  mission snapshot is ENU z-up with lat/lon (`docs/semantic-map-snapshot.md`). The agent-facing 3D
  contract must name its frame and up axis.
- **Frames:** full resolution `PreparedDataset.frame_path(channel, t_ns)` (PNG, EuRoC layout);
  recorded runs keep display JPEGs (`RunHistoryStore.frame_jpeg`). Crop helpers exist:
  `mission/demo.py:322 detection_crop_jpeg`, `segbench/fusion.py:226 crop_jpeg`.
- **No frontend toolchain:** no `package.json` anywhere; demo UI is HTML/JS inside Python strings.
  A shadcn chat app is a new `web/` package with its own CI workflow (precedent:
  `.github/workflows/bevy-wasm-*.yml` for `examples/bevy-sitl-poc`).
- **Scope guardrail holds:** tools launch demos/replays and read results; nothing commands a
  vehicle (AGENTS.md § Scope guardrail, `docs/architecture.md` §1).

## Exploration 1 — SurMap services the tools wrap

Sequence: repository-wide greps for `tool_calls|"tools"|max_turns|agentic|langgraph`, reads of
`src/surmap/{demo,mission,survey,slam,labelling,mapqa,rpc}`, `proto/`, `scripts/`, `docs/`,
`pyproject.toml`, `.github/workflows/ci.yml`; diff scan of every local and remote branch against
`main` for agent-loop code (none — hits were older copies of merged tool-call code).

### Demos
- `scripts/demo.py` → `make_demo_server(...)` (`demo/server.py:1527`), port 8765; flags
  `--dataset --frames --start --fps --no-rtabmap --rtabmap-mode --sam-* --history-db`.
- Scenes: `demo/datasets.py:125 DATASETS` — `euroc-v1-01-easy` (prompt `box`, 20 Hz),
  `kitti-2011-09-26-drive-0009` (`car`, 10 Hz), `ntu-viral-sbs-01` (`person`, 10 Hz). `DatasetSpec`
  at `:98`; cache `$SURMAP_DEMO_CACHE_DIR` or `~/.cache/surmap/demo-datasets`; `PrepareProgress`.
- Run: `GET /stream?dataset=&prompt=` → `start_run` → `_take_over` (cancels previous run, 10 s) →
  `_RunEngine` thread playing `DemoPlayer(...).events()`; events `run, frame, map, detections, sam,
  region, surface, status, final, ended`. Replay `GET /stream?replay=RUN`, rebuild
  `?rebuild_rtabmap=RUN`. Control `POST /control`.
- History: SQLite `<cache>/demo-history.db` (`demo/history.py:62-140`): `runs, frames, maps,
  detections, surface_points, events, run_rigs, dense_frames, run_sources`; reads `list_runs,
  get_run, timeline, snapshot_at, sam_at, frame_jpeg, dense_frame, surfaces_at`.
- `.surmaprun` archives: `demo/run_archive.py` `export_from`, `import_into`.
- Mission: `scripts/mission_demo.py` (port 8770) → `mission/demo.py` `run_offline_mission(:408)`,
  `run_live_mission(:467)`, `run_recorded_mission(:1283)` returning `MissionResult` (`:159`);
  synchronous, no progress callback.

### SAM
- Ports `survey/sam.py`: `RawFrame` (26), `SamDetection(label, score, box_xyxy, mask_polygon,
  track_id)` (39), `SamDetector.detect` async (57), `VideoSamDetector.reset/track/close` (64),
  `VideoSamStreamer.stream` (82); fakes `InMemory*`, `CentredBoxVideoSamDetector` (193).
- Adapters: `meta_sam.py:246 MetaSamDetector` (`sam-3.1`), `modal_sam.py:228`, `ollama_box.py:31`
  (sync), `sam3.py` ONNX, `sam3_torch.py` (cuda/mps), `demo/remote.py:513 RemoteSamDetector`.
- Text concepts only; no point/box prompts.

### Objects and 3D
- `demo/events.py:131 RegionPlacer.region_event` → `:205 SurfaceAssigner.surface_event`;
  surfaces by voxel-overlap continuation (`survey/surfaces.py:1-42`, 10 cm grid, moving after
  40 cm drift). `SurfaceMap.surfaces()` (222). Object feed `demo/object_feed.py`.
- Mission objects: `mission/objects.py:35 ObjectMerger`; snapshot `map/snapshot.py`.
- Dense depth: `slam/dense.py:128 DenseFrame`, `:389 dense_region_points`.
- 2D hulls only (`moving/areas.py:84`, `viewer/project.py:191`).

### Frames
- `PreparedDataset.frame_path(channel, t_ns)` (`datasets.py:284-290`), display JPEG cache
  `display-WxH/cam{c}/{t_ns}.jpg`, `RunHistoryStore.frame_jpeg(run_id, frame_id)`.
- Crops: `mission/demo.py:322 detection_crop_jpeg(image, box, pad=16)`,
  `segbench/fusion.py:226 crop_jpeg(image, box_xyxy, padding_px)`.

### Proto / RPC
- `proto/surmap/survey/v1/survey.proto`: `Cm5SurveyService`, `StationSamService`.
- Codegen `uv run --with grpcio-tools==1.73.1 python scripts/gen_survey_rpc.py`; outputs in
  `src/surmap/survey/proto/` (checked in, ruff per-file ignores in `pyproject.toml`).
- `rpc/compose.py Brick`, `rpc/description.py ServiceModule/ServerDescription`,
  `rpc/hosts/hypercorn.py HypercornHost`, `rpc/hosts/in_memory.py InMemoryHost`,
  `rpc/testkit RecordingBrick`. End-to-end example `survey/station_server.py` +
  `survey/station_main.py:77-92`; tests `tests/test_survey_station_server.py`,
  `tests/test_survey_entrypoints.py:100-116`, `tests/test_survey_server_e2e.py:27-35`.

### LLM clients
| Client | API | Tools |
|---|---|---|
| `labelling/meta_muse.py` Scene/Label/Concept | Meta Responses | no (`text.format` schema only) |
| `mapqa/client.py MetaClient` | Meta Responses | no |
| `labelling/baseten_muse.py` | OpenAI chat completions | yes (`record_label`) |
| `labelling/modal_muse.py` | OpenAI-compatible | not wired |
| `labelling/ollama.py` | Ollama `/api/chat` | no |

Transports are small typed protocols (`MetaMuseTransport.post_json`, `HttpTransport.post`,
`OllamaTransport.post_json`) — easy to fake.

### Dependencies, tests, CI
- Runtime deps: ai-edge-litert, connectrpc==0.12.1, googleapis-common-protos, h2, hypercorn,
  meta-sam-parser, numpy, onnxruntime, pillow, protobuf>=6.33,<7, protobuf-py==0.5.0, rosbags,
  websockets. Dev: mypy, pytest, pytest-asyncio, ruff, types-protobuf. mypy strict over `src` and
  `tests`.
- Tests flat `tests/test_<area>_<topic>.py`, `asyncio_mode = "auto"`, Given/When/Then; live calls
  gated by `SURMAP_LIVE_*`; `tests/mapqa_fakes.py RecordingTransport`.
- CI `.github/workflows/ci.yml` job `test` (3.11, 3.12): uv sync, ruff check, ruff format --check,
  mypy, pytest -q; plus rtabmap/coral e2e jobs.

### Deferred work touching the stack
- `src/surmap/docs/code-issues/oversized-file-demo-server.md` — `demo/server.py` 2,215 lines;
  suggested split `demo/workers.py, display.py, floor_plan.py, http.py`. Relevant to n2.
- `src/surmap/docs/code-issues/oversized-file-demo-page.md` — `demo/page.py` 715 lines. Not
  touched by this stack (the chat UI is a separate app).
- `src/surmap/docs/todo/2026-10-27-live-ros2-connectrpc-bridge.md`,
  `2026-10-27-gps-on-survey-wire-proto.md` — RPC TODOs, not touched.

## Exploration 2 — 3D formats for LLM agents

- **OBJ text with quantised integer coordinates** is the format LLMs are trained on for meshes:
  LLaMA-Mesh (https://arxiv.org/abs/2411.09595) scales to [0,64] and rounds to integers because
  floats produce long token sequences; MeshLLM (https://arxiv.org/pdf/2508.01242) keeps integer
  OBJ. Points are `v` lines; meshes add `f` lines, so one reader covers both.
- **Point-cloud LLMs read encoder embeddings, not text** (PointLLM https://arxiv.org/abs/2308.16911,
  GPT4Point https://arxiv.org/abs/2312.02980): raw coordinates in context are a last resort.
- **Summaries beat raw geometry for reasoning:** ConceptGraphs (https://arxiv.org/abs/2309.16650)
  and SceneGPT (https://arxiv.org/abs/2408.06926) give the LLM per-object JSON (id, bbox centre and
  extent, tag, caption); SayPlan (https://proceedings.mlr.press/v229/rana23a.html) expands and
  collapses a scene graph through tools instead of dumping it; LLM-Grounder
  (https://arxiv.org/abs/2309.12311) returns boxes plus derived facts (volume, distances).
- **Vision models do better from several rendered views** (https://arxiv.org/abs/2401.07572).
- **Exchange format:** glTF 2.0 / GLB — primitive mode POINTS (0) now, TRIANGLES (4) later,
  `COLOR_0`, optional `KHR_mesh_quantization` / `EXT_meshopt_compression`
  (https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html); three.js loads it natively.
  glTF JSON's base64 buffers are opaque to an LLM — transport, not context.
- **Handle + summary pattern:** return a summary and a URI instead of geometry
  (https://modelcontextprotocol.io/specification/2025-06-18/server/tools `resource_link` +
  `structuredContent`).
- **CityJSON** (https://www.cityjson.org/specs/2.0.1/) quantises with `transform.scale/translate`
  and carries surface semantics — a later export for buildings, not the agent contract.

Decided contract: per object an always-present summary JSON (id, label, confidence, frame, up axis,
units, centroid, OBB centre/extents/rotation from PCA, AABB, height, footprint area, point/face
counts, shape class from PCA eigenvalue ratios, observed frames and time span, neighbours with
distance and relation, `geometry_uri`); on request `surmap-obj v1` text (OBJ `v`/`f`, integer cm
relative to the OBB centre, voxel 5 cm then cap ~500 points / ~1,000 faces, `# decimated from N`);
GLB for the viewer and other tools.

## Exploration 3 — agent design patterns adopted

Patterns taken from prior LangGraph agent work the developer pointed at (not named in this repo):

- Graph per turn: `model → tools → model …` with a `cut_off` node; END when the model asks for no
  tools; round cap (default 50, env override) and a repeated-identical-failure cap (3) route to
  `cut_off`, which answers unanswered calls with "Not run" tool messages. Tool calls in one model
  batch run one at a time. State `messages` uses `operator.add`. No checkpointer: history comes
  from a conversation store and is appended round by round. `recursion_limit = 2*cap + 4`.
- Tool errors never end a turn: a failed handler becomes a failed tool result; `CancelledError`
  still propagates.
- Tools defined as proto services: the rpc's **leading comment** is the tool description, field
  comments are parameter descriptions, rpc `StartCompute` → tool `start_compute`. Codegen reads the
  `FileDescriptorSet` (with source info) and emits per tool a JSON schema for validation and a
  provider-portable schema handed to `bind_tools` as a dict (pydantic models dropped enums).
  Dispatch in the agent is in process; the same tools are also served as RPCs from the
  descriptor.
- Long work is a job: the tool returns a handle at once; terminal job transitions start a
  server-side turn whose opening message is a system notice; a `wait_for_jobs` tool (ceiling
  300 s) lets the model block deliberately. Prompt rules: say a job started, never that it
  finished; name the job id.
- What that prior work lacks and this stack adds: a per-call timeout with a post-timeout policy
  (fail vs. detach to async), and steering (a pending message pushed while a turn runs, which
  detaches in-flight blocking calls). Prior work rejected a second message during a turn.
- Testing: a scripted fake chat model (`BaseChatModel` returning scripted `AIMessage`s, repeating
  the last so a tool loop hits the cap, recording seen histories and bound tools, with a hold hook
  for cancellation tests); everything else (graph, tool node, stores) runs for real.
- Chat UI: React + Vite + Tailwind + connect-es v2 / protobuf-es; transcript as a discriminated
  union of roles; tool calls as collapsible steps with a status icon; job progress components.
