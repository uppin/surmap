# Changeset: Station SAM analysis policy

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package, concurrency/ordering semantics at the gate, async tests

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/` — neither exists
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Stub API — `SamDetector`, `AnalysisGate`, `InMemorySamDetector` signatures (`TODO(pr-3)`)
  - [ ] Create failing acceptance tests
  - [ ] Run acceptance tests (verify they fail)
  - [ ] TDD Red — write failing unit/integration tests
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Gate admits serially under `EVERY_FRAME`
  - [ ] Gate drops + counts under `BEST_EFFORT_DROP` when busy
  - [ ] Fake detector returns configured detections
  - [ ] Acceptance: policy tests pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-27-station-sam-policy-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: new `src/surmap/survey/sam.py` (port, policy, fake)

## Summary

Adds the station's SAM seam: a detector port, the every-frame vs
best-effort-drop admission gate, and an in-memory detector for tests.

## Background

SAM 3.1 on the station GPU is the pipeline's scarce resource
(architecture §3.1; throughput unverified on the target card). The
requester chooses the trade-off per stream: lag or drops. That choice
must be enforceable and testable without a GPU or a server.

## Scope

- **Implementation**: `SamDetection`, `SamDetector` protocol, `AnalysisGate`, `InMemorySamDetector`
- **Testing**: async unit tests for both modes and the fake

## Technical Changes

### State A (Current)

- No SAM port or policy; nothing states what happens under load.

### State B (Target)

- `surmap.survey.sam.SamDetection`: frozen dataclass (label, score,
  box_xyxy, mask_polygon, track_id optional).
- `SamDetector` protocol: `async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]`
  where `RawFrame` is this module's frame value (frame_id, t_ns, channel,
  width, height, encoding, data).
- `AnalysisGate(mode)`: async context manager `slot()` yielding `True`
  when the caller may analyze, `False` when the frame is dropped
  (best-effort + busy); `dropped` counts drops. One analysis at a time.
- `InMemorySamDetector(detections)`: fake returning configured detections.

### Delta (What's Changing)

#### surmap

- **Implementation**: new module; the `AnalysisMode` proto enum (n1) is
  mapped onto this gate by the station server (n5), not imported here

## Verification

**Method:** V1 fail→pass — policy/fake tests fail against the stubs, pass after
**Command:** `uv run pytest -q tests/test_survey_sam_policy.py`
**Before:** tests fail (`NotImplementedError` from the stubs)
**After:** tests pass

## Testing Plan

**Primary Test Approach:** Unit (async) — a controllably slow fake
detector proves serialization under `EVERY_FRAME` and drop+count under
`BEST_EFFORT_DROP`; no timing sleeps that decide outcomes (events, not
clocks).

## Acceptance Tests

### surmap

- **Unit**: `tests/test_survey_sam_policy.py` — both admission modes + fake

## Inherited Dependencies — do not implement here

Symbols this PR builds on that a **predecessor owns**. They arrive as stubs; implementing them here
would collide with the PR that owns them.

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `AnalysisMode` proto enum (`surmap.survey.v1`) | n1 | contract only | defines its own domain behaviour; n5 maps the enum onto this gate — this PR never imports the generated bindings |

**Greenable independently?** yes — the gate is specified in domain terms; the enum mapping is n5's.

## Stack Context

**Stack**: Survey streaming · slug **`#survey-stream`** — this PR is **3 of 5** · #pending
**Branch**: `pr-3-station-sam-policy` · **Base**: `pr-2-cm5-point-emitter`
**Successor**: `pr-4-cm5-survey-server`
**Kind**: Feature · behaviour-adds — `(Type: Feature, Behaviour: adds)`
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance tests

Why the boundary falls here: admission policy is one async rule;
the station server (n5) should enforce it, not contain it.

### Owned API surface

- `surmap.survey.sam`: `SamDetection`, `RawFrame`, `SamDetector`, `AnalysisGate`, `InMemorySamDetector`

### Green wave

**Wave:** 1 of 2
**Node:** n3 — this PR's position in the stack
**Concurrent with:** n1, n2
**Blocks:** n5 (its per-frame analysis is admitted by this gate)

Real dependency edges, as opposed to the branch line:

    n1 → n4, n5      n2 → n4      n3 → n5

### Greenable independently?

**yes** — it owns everything its tests drive.

### Trunk-merge safety

**When this PR merges alone:** production deploy/runtime and local dev
workflows stay working (`uv run pytest -q`, `uv run mypy` — an unused
module + fake). **Local dev data:** no. **Production data:** none.
