# Changeset: CM5 incremental point emitter

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — one package, pure logic, unit-level tests

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/` — neither exists
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Stub API — `IncrementalPointEmitter` signatures (`TODO(pr-2)`)
  - [ ] Create failing acceptance tests
  - [ ] Run acceptance tests (verify they fail)
  - [ ] TDD Red — write failing unit/integration tests
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `emit` forwards spawn-only points per designation
  - [ ] `reset` clears the seen-set
  - [ ] Acceptance: emitter tests pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-27-cm5-point-emitter-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: new `src/surmap/survey/points.py`

## Summary

Adds the spawn-only point emitter the CM5 server streams through:
per designation, per stream, a point at an already-sent position is
never resent.

## Background

RTAB-Map and object reconstruction return full per-frame point sets.
Streaming those verbatim would resend the static scene on every frame;
the CM5 uplink (§8) cannot assume bandwidth. Dedup must be exact and
per designation so object layers never suppress scene points.

## Scope

- **Implementation**: `IncrementalPointEmitter.emit/reset` over `Vec3`
- **Testing**: unit tests for spawn-only, per-designation, reset semantics

## Technical Changes

### State A (Current)

- No emitter; producers' points would be streamed in full every frame.

### State B (Target)

- `surmap.survey.points.IncrementalPointEmitter`:
  `emit(designation: int, points: Iterable[Vec3]) -> tuple[Vec3, ...]`
  returns, in input order, points whose `(designation, x, y, z)` was not
  seen before in this stream, recording them as seen; duplicates within
  one call are also suppressed. `reset()` clears all seen state.

### Delta (What's Changing)

#### surmap

- **Implementation**: new pure-logic module; no proto or I/O dependency

## Verification

**Method:** V1 fail→pass — emitter tests fail against the stub, pass after
**Command:** `uv run pytest -q tests/test_survey_points.py`
**Before:** tests fail (`NotImplementedError` from the stub)
**After:** tests pass

## Testing Plan

**Primary Test Approach:** Unit — deterministic in-memory point sets;
first emission, identical re-emission, moved point, duplicate within a
batch, per-designation independence, reset.

## Acceptance Tests

### surmap

- **Unit**: `tests/test_survey_points.py` — spawn-only dedup semantics

## Inherited Dependencies — do not implement here

Symbols this PR builds on that a **predecessor owns**. They arrive as stubs; implementing them here
would collide with the PR that owns them.

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `surmap.survey.designations` constants (`RTABMAP_DESIGNATION`, `object_designation`) | n1 | stub signatures, `TODO(pr-1)` | accepts designation as a plain `int`; tests pass literal designations, never import the helpers |

**Greenable independently?** yes — designation is an opaque int here; no predecessor behaviour is driven.

## Stack Context

**Stack**: Survey streaming · slug **`#survey-stream`** — this PR is **2 of 5** · #pending
**Branch**: `pr-2-cm5-point-emitter` · **Base**: `pr-1-survey-proto`
**Successor**: `pr-3-station-sam-policy`
**Kind**: Feature · behaviour-adds — `(Type: Feature, Behaviour: adds)`
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance tests

Why the boundary falls here: dedup is one pure rule over `Vec3`; the
CM5 server (n4) should consume it, not contain it.

### Owned API surface

- `surmap.survey.points.IncrementalPointEmitter` (`emit`, `reset`)

### Green wave

**Wave:** 1 of 2
**Node:** n2 — this PR's position in the stack
**Concurrent with:** n1, n3
**Blocks:** n4 (its point streaming forwards through this emitter)

Real dependency edges, as opposed to the branch line:

    n1 → n4, n5      n2 → n4      n3 → n5

### Greenable independently?

**yes** — it owns everything its tests drive (designation is an opaque int).

### Trunk-merge safety

**When this PR merges alone:** production deploy/runtime and local dev
workflows stay working (`uv run pytest -q`, `uv run mypy` — an unused
pure module). **Local dev data:** no. **Production data:** none.
