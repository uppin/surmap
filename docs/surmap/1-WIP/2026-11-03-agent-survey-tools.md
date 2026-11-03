# Changeset: Survey agent tools — demos, SAM, objects, 3D and frames

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — eight tools across demo, SAM, history and 3D seams; integration tests on the EuRoC fixture; inherited restructure to build on

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (commit 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: `SurveyWorkspace` port + adapter over `DemoRunHost` and `RunHistoryStore` (headless start, wait for end)
  - [ ] Milestone 2: `list_demos`, `run_demo`, `get_run`
  - [ ] Milestone 3: `prompt_sam` on a recorded run's frames
  - [ ] Milestone 4: `find_objects`, `get_object`, `get_object_geometry` (summaries via `surmap.objects3d`, GLB store)
  - [ ] Milestone 5: `get_frame` with crop by box or object, max side, image result
  - [ ] Milestone 6: `survey_tool_handlers(workspace)` plugs into `survey_tools_module` and the runtime's tool binding
  - [ ] Acceptance: `tests/test_agent_tools_demo.py`, `tests/test_agent_tools_objects.py`, `tests/test_agent_tools_frames.py` pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/agent.md` — "Tools" section: one row per tool with arguments, result and default execution
  - [ ] `docs/surmap/changelog/2026-11-03-agent-survey-tools.md` — write changelog entry
  - [ ] Validate tests (`/validate-tests`)
  - [ ] (optional) Production readiness validated — run if `run_demo` can leave a run engine alive after a cancelled job

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-agent-survey-tools-initial-discovery.md](./2026-11-03-agent-survey-tools-initial-discovery.md).

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **7 of 9** · #pending
**Branch**: `pr-7-survey-agent` · **Base**: `pr-6-survey-agent`
**Successor**: `pr-8-survey-agent`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance and unit tests

Why the boundary falls here: tool handlers are where SurMap's domain meets the agent contract. They
take decoded proto requests and return proto responses, so they test without a model or a server.

### Owned API surface

- `surmap.agent.tools.workspace`: `SurveyWorkspace` (protocol), `DemoWorkspace` (adapter over
  `DemoRunHost` + `RunHistoryStore` + scene cache), `GeometryStore` (GLB by `(run_id, object_id)`)
- `surmap.agent.tools.handlers`: `survey_tool_handlers(workspace) -> Mapping[str, Handler]` and
  one handler per `SurveyTools` rpc
- `surmap.agent.tools.frames`: `frame_image(...)`, `crop_box_for_object(...)`

### Green wave

**Wave:** 2 of 4
**Node:** n7
**Concurrent with:** none — this node is alone in its wave
**Blocks:** n8 (serves these handlers and binds them as agent tools)

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9

### Greenable independently?

**no — blocked by n1, n2 and n3**: the acceptance tests mount handlers on `survey_tools_module` (n1),
start runs through `DemoRunHost` (n2) and assert `ObjectSummary` fields and OBJ text (n3). Tests red
because those are still stubs are blocked-on-n1/n2/n3, not failures.

### Trunk-merge safety

**When this PR merges alone:** additive; the demo server is not modified (the adapter only
constructs a `DemoRunHost`). `uv run pytest -q` unchanged outside the new tests. **Local dev data:**
runs the tests start go to a temp history DB, never `~/.cache/surmap`. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `surmap.agent.v1` messages, `survey_tools_module`, `ToolContract` | n1 | real after n1 green | implements handlers on its messages; does not edit protos |
| `surmap.demo.runs.DemoRunHost` | n2 | real after n2 green | constructs it headlessly; does not move demo code |
| `surmap.objects3d.summarize`, `encode_obj_text`, `write_glb` | n3 | real after n3 green | calls them; does not implement geometry |
| `JobRunner` / `bind_contract_tool` | n4 | not needed by these tests | handlers are plain async functions; binding happens in n8 |

**Greenable independently?** no — needs n1, n2, n3 green first.

## Inherited Restructure — expect rewrite

| What moves | From → To | Owned by | Effect here |
|---|---|---|---|
| `_RunEngine`, run/scene methods of `_DemoHttpServer` | `demo/server.py` → `demo/runs.py` (`DemoRunHost`) | n2 | this node's red tests import `surmap.demo.runs.DemoRunHost`, which exists only after n2's green |

**Repair**: after n2's `/code-restructuring` lands, run `/pr-stack-rebase` here, then fix the fallout
in **a new commit on this branch**. Each red test must still fail for this PR's missing handlers.

## Affected Packages

- **surmap** (`src/surmap/agent/tools`).

## Related Feature Documentation

- PRD: [PRD-2026-11-03-agent-survey-tools.md](./PRD-2026-11-03-agent-survey-tools.md)

## Summary

Eight handlers behind a `SurveyWorkspace` port. The default adapter drives the demo's run host
headlessly and reads the run history; tests use the tiny EuRoC fixture and a fake SAM detector.

## Background

Runs start today only through SSE `GET /stream` (`demo/server.py:1326`); after n2 the same lifecycle
is `DemoRunHost.start_run`, which returns a `_RunEngine` whose `done` event ends the run. SAM is
per run (`demo/sam_prompt.py`); `prompt_sam` therefore runs a detector on stored frames of a recorded
run instead of re-prompting a live one.

## Scope

- Handlers, workspace port and adapter, GLB store, frame/crop helpers
- **Out of scope:** binding to the runtime and serving (n8); the mission demo (no run history)

## Technical Changes

### State A (Current)

`RunHistoryStore` reads (`list_runs, get_run, timeline, sam_at, frame_jpeg, surfaces_at`),
`PreparedDataset.frame_path`, crop helpers `mission/demo.py:322`, `segbench/fusion.py:226`, SAM ports
in `survey/sam.py` with `CentredBoxVideoSamDetector` (193) for fakes.

### State B (Target)

```python
class SurveyWorkspace(Protocol):
    def scenes(self) -> Sequence[SceneInfo]: ...
    async def run_demo(self, dataset: str, prompt: str | None, *, frames: int | None, fps: float | None) -> RunInfo: ...
    def run(self, run_id: str) -> RunInfo | None: ...
    async def detect(self, run_id: str, concept: str, frame_ids: Sequence[str]) -> Sequence[FrameDetections]: ...
    def objects(self, run_id: str) -> Sequence[StoredObject]: ...        # points + label + frames
    def frame(self, run_id: str, frame_ref: FrameRef) -> FrameImage: ...  # bytes, media type, size, source

async def run_demo(req: agent_pb2.RunDemoRequest, ws: SurveyWorkspace) -> agent_pb2.RunDemoResponse: ...
```

`run_demo` awaits the engine's `done` in a thread (`asyncio.to_thread`) so the runtime can detach or
cancel it; a cancelled job stops the engine.

### Delta (What's Changing)

#### surmap

- `src/surmap/agent/tools/{__init__,workspace,handlers,frames}.py` (new)

## Verification

**Method:** V1 — fail→pass acceptance and integration tests
**Command:** `uv run pytest -q tests/test_agent_tools_demo.py tests/test_agent_tools_objects.py tests/test_agent_tools_frames.py`
**Before:** red — handlers raise `NotImplementedError` (and blocked on n1–n3 stubs until they green)
**After:** green, offline (fake SAM, tiny EuRoC fixture, no RTAB-Map)

## Testing Plan

- Workspace adapter built on a temp cache with the tiny EuRoC zip (`tests/test_demo.py` builder),
  `with_rtabmap=False`, `CentredBoxVideoSamDetector`.
- Object tools on a history DB seeded with surfaces of known shape.
- Frame tools on the fixture's PNG frames; crop sizes checked with Pillow.

## Acceptance Tests

### surmap

- `tests/test_agent_tools_demo.py` — `list_demos` scenes and prompts; `run_demo` ends with frames > 0; `get_run` matches; cancelling the call stops the engine
- `tests/test_agent_tools_objects.py` — `prompt_sam` detections per chosen frame; `find_objects` by label and `near`; `get_object` summary; `get_object_geometry` OBJ within limits and resolvable GLB URI
- `tests/test_agent_tools_frames.py` — full-resolution frame when cached, display JPEG otherwise; crop by box; crop by object id contains its box; `max_side` respected

## Decisions & Trade-offs

- **`prompt_sam` on recorded frames, not a live re-prompt**: the demo fixes the prompt per run by
  design (`docs/surmap/changelog/2026-10-31-demo-sam-prompt.md`); a new live prompt is `run_demo`.
- **Headless runs share the demo's history DB** (configurable path) so the console shows agent runs;
  a headless run takes over a running console run exactly as a new viewer would.
- **Images go back as image content**, not base64 inside JSON; the binding in n8 turns `GetFrameResponse.image` into a model image part.
