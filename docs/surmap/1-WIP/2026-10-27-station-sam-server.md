# Changeset: Station SAM server

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — proto/contract consumption, async BIDI handler, analysis concurrency semantics

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file @ `8beffa8`
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/` — neither exists
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-10-27 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 4 tests red at import: `survey_pb2` bindings not yet generated (n1 stub state); after n1/n3 green they fail on this node's `NotImplementedError` stubs (commit 2). Baseline 359 green excluding inherited red files
  - [x] Stub API — handler + brick factory signatures (`TODO(pr-5)`)
  - [x] Create failing acceptance tests
  - [x] Run acceptance tests (verify they fail)
  - [x] TDD Red — write failing unit/integration tests
- [wf 3] ✅ 2026-10-27 `/green` Green — implement until every red test passes · 4/4 station tests pass (twice, deterministic), 389 full suite pass; `station_server.py` clean under mypy strict + ruff (1 pre-existing mypy error in `tests/test_survey_station_server.py:32` and 1 pre-existing ruff error in `tests/test_survey_cm5_server.py:1`, both untouched by this PR)
  - [x] Config-first stream; map `AnalysisMode` onto the gate
  - [x] Answer admitted frames with `SamFrameDetections` keyed by `frame_id`
  - [x] Drop (no response) for frames the gate refuses under best-effort
  - [x] Acceptance: station stream tests pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/architecture.md` §10 — GPU API served by `StationSamService`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-27-station-sam-server-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: new `src/surmap/survey/station_server.py`

## Summary

Adds the station ConnectRPC BIDI server: the CM5's frame input in,
SAM detection vectors keyed by `frame_id` out, with the requester's
every-frame vs best-effort-drop choice enforced.

## Background

Architecture §4.2 puts SAM segmentation on the station, fed by the same
frames the CM5 consumes. Requesters must be able to trade latency for
completeness explicitly (n3's gate), and reconcile answers by the
`frame_id` they assigned.

## Scope

- **Implementation**: BIDI handler, enum→gate mapping, rpc brick/description factory
- **Testing**: async handler tests (fake detectors incl. a slow one); one in-process Connect BIDI test via `InMemoryHost`

## Technical Changes

### State A (Current)

- No station server; SAM has no streaming input or defined output.

### State B (Target)

- `surmap.survey.station_server.stream_analysis(requests, detector, gate_factory)`:
  first request must be config (else Connect `INVALID_ARGUMENT`); each
  frame is admitted through a gate built from the config's mode;
  admitted frames are converted to `surmap.survey.sam.RawFrame`, analyzed,
  and answered as `SamFrameDetections` in analysis order; dropped frames
  produce no response. Detection conversion preserves label, score, box,
  mask polygon, and optional track id.
- `station_service_module()` brick factory for `surmap.rpc` hosts.

### Delta (What's Changing)

#### surmap

- **API**: `StationSamService` served; handler is the owned surface

## Verification

**Method:** V1 fail→pass — stream tests fail against the stubs, pass after
**Command:** `uv run pytest -q tests/test_survey_station_server.py`
**Before:** tests fail (`NotImplementedError` from the stubs)
**After:** tests pass

## Testing Plan

**Primary Test Approach:** Integration at the handler level (async
generators in/out; `InMemorySamDetector` for content, an event-controlled
slow fake for drop behaviour — determinism via events, never sleeps),
plus one BIDI round-trip through `InMemoryHost`.

## Acceptance Tests

### surmap

- **Integration**: `tests/test_survey_station_server.py` — frame_id-keyed vectors, both modes, config-first error

## Inherited Dependencies — do not implement here

Symbols this PR builds on that a **predecessor owns**. They arrive as stubs; implementing them here
would collide with the PR that owns them.

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `surmap.survey.v1` messages, `StationSamService` descriptor, `AnalysisMode` enum | n1 | generated contract (stub until n1 greens) | consumes and maps the enum; never edits the proto |
| `AnalysisGate`, `SamDetector`, `InMemorySamDetector` | n3 | stub, `TODO(pr-3)` | constructs the gate from the mapped mode and calls the port; drop-behaviour tests are blocked on n3 green (below) |

**Greenable independently?** no — needs n1 and n3 green first: its acceptance tests drive the real generated messages and the real gate.

## Stack Context

**Stack**: Survey streaming · slug **`#survey-stream`** — this PR is **5 of 5** · [#11](https://github.com/uppin/surmap/pull/11)
**Branch**: `pr-5-station-sam-server` · **Base**: `pr-4-cm5-survey-server`
**Successor**: none — top of stack
**Kind**: Feature · behaviour-adds — `(Type: Feature, Behaviour: adds)`
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance tests

Why the boundary falls here: transport + reconciliation here; the
admission rule and detector port are owned below it (n3).

### Owned API surface

- `surmap.survey.station_server`: `stream_analysis`, `station_service_module`

### Green wave

**Wave:** 2 of 2
**Node:** n5 — this PR's position in the stack
**Concurrent with:** n4
**Blocks:** nothing

Real dependency edges, as opposed to the branch line:

    n1 → n4, n5      n2 → n4      n3 → n5

### Greenable independently?

**no — blocked by n1, n3**: its tests drive n1's real generated messages
and n3's real gate.

### Trunk-merge safety

**When this PR merges alone:** production deploy/runtime and local dev
workflows stay working (`uv run pytest -q`, `uv run mypy`; mountable
service, no shipped entrypoint mounts it yet). **Local dev data:** no.
**Production data:** none.
