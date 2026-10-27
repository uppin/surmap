# Changeset: Survey streaming proto contracts

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — proto/contract change, generated bindings, plus a directed `.agents/` docs cleanup in the same node

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file @ `555892f`
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/` — neither exists; package never analyzed, noted in discovery
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-10-27 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 10 tests red: proto tests fail on missing `survey_pb2` bindings, helper tests on `NotImplementedError` stubs (commit 2)
  - [x] Stub API — `.proto` contract + designation helper signatures (`TODO(pr-1)`)
  - [x] Create failing acceptance tests
  - [x] Run acceptance tests (verify they fail)
  - [x] TDD Red — write failing unit/integration tests
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Generate and check in `survey_pb2` bindings + generation script
  - [ ] Implement designation helpers
  - [ ] Remove overstack references from `.agents/` stack docs (see Decisions)
  - [ ] Acceptance: proto descriptor tests pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/connectrpc.md` — note the survey service bindings and regen command
  - [ ] `docs/architecture.md` §10 — name `surmap.survey.v1` as the Board/GPU wire contract

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-27-survey-proto-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: proto + generated bindings under `proto/surmap/survey/v1/` and `src/surmap/survey/v1/`; designation helpers under `src/surmap/survey/`
  - [architecture.md](../../architecture.md) §10 — wire contract named at wrap
  - [connectrpc.md](../../connectrpc.md) — bindings/regen noted at wrap
- **agent workflow docs** (`.agents/`): pr-stack skill and stack commands lose the overstack epic machinery (Green-row deliverable, this node only)

## Summary

Adds the `surmap.survey.v1` protobuf contract — two BIDI streaming
services, shared frame/calibration input, designated point/video output,
SAM detection vectors, and Python designation helpers — and removes the
unavailable overstack tooling references from the stack workflow docs.

## Background

Architecture §10 requires Board and GPU APIs; no wire format exists.
Successor nodes (CM5 server, station server) need a compiled contract to
build against. The overstack epic CLI referenced by the stack workflow
does not exist in this repo, so planning stalls on it; the developer
directed its removal in this node.

## Scope

- **Implementation**: `survey.proto`, generation script, checked-in bindings, designation helpers
- **Docs cleanup**: overstack/epic references removed from `.agents/` stack skill + commands
- **Testing**: descriptor/contract acceptance tests, helper unit tests

## Technical Changes

### State A (Current)

- Only proto is `surmap.transport.v1` (socket framing, no services).
- No `surmap.survey` package; no designation scheme; SAM output undefined.
- `.agents/` stack docs mandate an epic issue via unavailable CLI tooling.

### State B (Target)

- `proto/surmap/survey/v1/survey.proto`: `Cm5SurveyService.StreamSurvey`
  and `StationSamService.StreamAnalysis`, both BIDI. Client streams open
  with a config message (`oneof`: config | frame). CM5 config carries
  `StereoCalibration` + requested video channels; station config also
  carries `AnalysisMode` (`EVERY_FRAME` | `BEST_EFFORT_DROP`) and optional
  concept prompts.
- CM5 responses are a `oneof`: `PointBatch{designation, frame_id, t_ns,
  points[]}` or `VideoFrameOut{designation, frame}`. Station responses are
  `SamFrameDetections{frame_id, detections[]{label, score, box_xyxy,
  mask_polygon[], track_id}}`.
- `src/surmap/survey/designations.py`: `RTABMAP_DESIGNATION=1`,
  `video_designation(channel)` → 2/3, `object_designation(track_id)` →
  `100+track_id`, each validating its input.
- `.agents/` stack docs: no overstack, no epic DAG; topology from
  `gh stack` + PR bases, waves in changesets/PR bodies.

### Delta (What's Changing)

#### surmap

- **API**: new `surmap.survey.v1` services and messages (above)
- **Implementation**: generated bindings + `scripts/gen_survey_rpc.py`

## Verification

**Method:** V1 fail→pass — contract tests fail before the bindings/helpers exist, pass after; plus V3 for the docs cleanup
**Command:** `uv run pytest -q tests/test_survey_proto.py tests/test_designations.py && grep -rn overstack .agents/ ; test $? -eq 1`
**Before:** tests fail (module missing); grep finds overstack in 6+ files under `.agents/`
**After:** tests pass; grep finds nothing

## Testing Plan

**Primary Test Approach:** Unit/integration at the descriptor level —
load the generated descriptor pool, assert both services are BIDI, every
message/field/enum exists with the approved numbers, and round-trip a
point batch and a detection frame through serialize/parse. Helper tests
assert the designation mapping and its validation errors.

## Acceptance Tests

### surmap

- **Integration**: `tests/test_survey_proto.py` — descriptor shape + message round-trips
- **Unit**: `tests/test_designations.py` — designation mapping/validation

## Decisions & Trade-offs

- **Overstack removal rides in this Feature node** at the developer's
  direction (2026-10-27), although it is behaviour-preserving docs work:
  it unblocks this stack's own planning, and splitting it into its own
  node would renumber the approved line. Its proof is the V3 grep above,
  recorded separately from the V1 contract tests.
- Designations are int32 constants + helpers, not a proto enum: object
  designations are open-ended (`100 + track_id`).

## Stack Context

**Stack**: Survey streaming · slug **`#survey-stream`** — this PR is **1 of 5** · [#6](https://github.com/uppin/surmap/pull/6)
**Branch**: `pr-1-survey-proto` · **Base**: `main`
**Successor**: `pr-2-cm5-point-emitter`
**Kind**: Feature · behaviour-adds — `(Type: Feature, Behaviour: adds)`
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance tests

Why the boundary falls here: every later node compiles against this
contract; it must land (and be generatable) before any server exists.

### Owned API surface

- `proto/surmap/survey/v1/survey.proto` and its generated bindings
- `scripts/gen_survey_rpc.py`
- `surmap.survey.designations` (constants + helpers)

### Green wave

**Wave:** 1 of 2
**Node:** n1 — this PR's position in the stack
**Concurrent with:** n2, n3
**Blocks:** n4 (needs the `Cm5SurveyService` messages to stream), n5 (needs the `StationSamService` messages and `AnalysisMode`)

Real dependency edges, as opposed to the branch line:

    n1 → n4, n5      n2 → n4      n3 → n5

### Greenable independently?

**yes** — it owns everything its tests drive.

### Trunk-merge safety

**When this PR merges alone:** production deploy/runtime and local dev
workflows stay working (`uv run pytest -q`, `uv run mypy` — contracts and
docs only, nothing served). **Local dev data:** no. **Production data:** none.
