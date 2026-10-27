# Changeset: CM5 survey server

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — proto/contract consumption, async BIDI handler, pairing + emitter ordering semantics

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file @ `4b7e4ad`
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/` — neither exists
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-10-27 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 6 tests red at import: `survey_pb2` bindings not yet generated (n1 stub state); after n1 greens they fail on this node's `NotImplementedError` stubs (commit 2). Baseline 359 green excluding inherited red files
  - [x] Stub API — handler, `ObjectPointSource` port, brick factory signatures (`TODO(pr-4)`)
  - [x] Create failing acceptance tests
  - [x] Run acceptance tests (verify they fail)
  - [x] TDD Red — write failing unit/integration tests
- [wf 3] ✅ 2026-10-27 `/green` Green — implement until every red test passes · 6 CM5 tests pass, 385 full suite pass, mypy clean; ruff clean on edited files (1 pre-existing F401 in tests/test_survey_cm5_server.py untouched)
  - [x] Pair frames by `frame_id`; run SLAM + object source per completed pair
  - [x] Stream emitter-filtered point batches (scene designation 1, objects per-object)
  - [x] Echo requested video channels under designations 2/3
  - [x] Acceptance: CM5 stream tests pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/architecture.md` §10 — Board API served by `Cm5SurveyService`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-27-cm5-survey-server-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: new `src/surmap/survey/cm5_server.py`, `src/surmap/survey/object_points.py` (port + fake)

## Summary

Adds the CM5 ConnectRPC BIDI server: frames + calibration in,
incremental designated points and requested video channels out.

## Background

The on-board pipeline (architecture §4.1) produces RTAB-Map scene points
and per-object points but has no live output; §8 assumes recording plus
a reduced live feed. This server is that feed, built on n1's contract,
n2's emitter, and the existing `SlamBackend` port.

## Scope

- **Implementation**: BIDI handler, stereo pairing, object-point port + in-memory adapter, rpc brick/description factory
- **Testing**: async handler tests over in-memory SLAM/object fakes; one in-process Connect BIDI test via `InMemoryHost`

## Technical Changes

### State A (Current)

- No server; on-board points have no streaming consumer.

### State B (Target)

- `surmap.survey.object_points.ObjectPointSource` protocol:
  `points_for_pair(pair: StereoFramePair, pose: Pose | None) -> tuple[ObjectPoints, ...]`,
  plus `InMemoryObjectPointSource` returning configured observations.
- `surmap.survey.cm5_server.stream_survey(requests, slam, objects, emitter)`:
  async generator implementing the approved semantics — first request
  must be config (else Connect `INVALID_ARGUMENT`); frames pair by
  `frame_id`; per completed pair, scene points (designation 1) and each
  object's points (its designation) pass through the emitter and yield
  as `PointBatch` in spawn order; frames on requested channels yield as
  `VideoFrameOut` in arrival order; an unposed pair (pose `None`) yields
  no map points (architecture §9: never place points with a guessed pose).
- `cm5_service_module()` brick factory for `surmap.rpc` hosts.

### Delta (What's Changing)

#### surmap

- **API**: `Cm5SurveyService` served; handler + port are the owned surface

## Verification

**Method:** V1 fail→pass — stream tests fail against the stubs, pass after
**Command:** `uv run pytest -q tests/test_survey_cm5_server.py`
**Before:** tests fail (`NotImplementedError` from the stubs)
**After:** tests pass

## Testing Plan

**Primary Test Approach:** Integration at the handler level (async
generators in/out, real emitter, in-memory SLAM/object adapters), plus
one BIDI round-trip through `InMemoryHost` to prove the descriptor,
brick, and handler compose. Deterministic scripted frame sequences;
assert exact output sequences (designation, frame_id, points).

## Acceptance Tests

### surmap

- **Integration**: `tests/test_survey_cm5_server.py` — pairing, dedup across frames, designations, video echo, unposed pair, config-first error

## Inherited Dependencies — do not implement here

Symbols this PR builds on that a **predecessor owns**. They arrive as stubs; implementing them here
would collide with the PR that owns them.

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `surmap.survey.v1` messages + `Cm5SurveyService` descriptor | n1 | generated contract (stub until n1 greens) | consumes the messages; never edits the proto |
| `IncrementalPointEmitter` | n2 | stub, `TODO(pr-2)` | calls `emit`; tests that need dedup behaviour are blocked on n2 green (below) |
| `surmap.survey.designations` helpers | n1 | stub, `TODO(pr-1)` | calls them for designations |

**Greenable independently?** no — needs n1 and n2 green first: its acceptance tests drive the real generated messages and the real emitter.

## Stack Context

**Stack**: Survey streaming · slug **`#survey-stream`** — this PR is **4 of 5** · [#10](https://github.com/uppin/surmap/pull/10)
**Branch**: `pr-4-cm5-survey-server` · **Base**: `pr-3-station-sam-policy`
**Successor**: `pr-5-station-sam-server`
**Kind**: Feature · behaviour-adds — `(Type: Feature, Behaviour: adds)`
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance tests

Why the boundary falls here: transport + pairing + ordering in one
place; the rules it applies (dedup, designations) are owned below it.

### Owned API surface

- `surmap.survey.cm5_server`: `stream_survey`, `cm5_service_module`
- `surmap.survey.object_points`: `ObjectPointSource`, `InMemoryObjectPointSource`

### Green wave

**Wave:** 2 of 2
**Node:** n4 — this PR's position in the stack
**Concurrent with:** n5
**Blocks:** nothing

Real dependency edges, as opposed to the branch line:

    n1 → n4, n5      n2 → n4      n3 → n5

### Greenable independently?

**no — blocked by n1, n2**: its tests drive n1's real generated messages
and n2's real emitter dedup.

### Trunk-merge safety

**When this PR merges alone:** production deploy/runtime and local dev
workflows stay working (`uv run pytest -q`, `uv run mypy`; the service
is mountable but nothing mounts it in a shipped entrypoint yet).
**Local dev data:** no. **Production data:** none.
