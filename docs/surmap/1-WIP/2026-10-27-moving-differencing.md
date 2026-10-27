# Changeset: Static-layer differencing and moving areas stream

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — proto/contract change, 5 Hz worker concurrency, one package

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-pr-stack` Plan — changeset, initial discovery · this file + companion; PRD = design doc (n1), §4 steps 1–2 + wire contract
  - [x] Record initial discovery
  - [x] Cross-check `docs/todo/` and `docs/code-issues/` — none exist for `src/surmap`
  - [x] Create/update PRD documentation — design doc on n1 serves as PRD (recorded in plan)
  - [x] Create changeset
- [wf 2] ⬜ `/plan-pr-stack` Red — owned stubs + failing tests committed ·
  - [ ] Stubs: `differencing.py` (`StaticLayer`, `tau`), `areas.py`, `config.py`
  - [ ] Failing tests: fast-car cluster persistence (issue 1), dwell absorption, τ pose term, polygon cap, association gate
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Proto `StreamMovingAreas` + regenerated bindings; `stream_moving_areas` handler
  - [ ] Static layer + differencing; mask→polygon + area tracks
  - [ ] EuRoC negative-control replay: zero rigid graduations (all `UNKNOWN` here)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/moving-object-detection-design.md` §4 — fold as-built step 1–2 notes

## Initial Discovery

Full exploration: [2026-10-27-moving-differencing-initial-discovery.md](./2026-10-27-moving-differencing-initial-discovery.md).

## Stack Context

**Stack**: moving-object detection · slug **`#moving-objects`** — this PR is **3 of 6** · #pending
**Branch**: `pr-3-moving-differencing` · **Base**: `pr-2-moving-snippets`
**Successor**: `pr-4-moving-classification`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = `/plan-red` stubs + failing tests

Why the boundary falls here: stages 1–2 (where change is) are one
reviewable capability; verdicts and keypoints are n4's surface.

### Owned API surface

- `proto/surmap/survey/v1/survey.proto` — `StreamMovingAreas`, `MovingArea`, `MovingObjectSnapshot`, `MovingAreasResponse`
- `src/surmap/moving/differencing.py`, `src/surmap/moving/areas.py`, `src/surmap/moving/config.py`
- `src/surmap/survey/cm5_server.py` — `stream_moving_areas`
- `tests/test_moving_differencing.py`, proto contract tests

### Green wave

**Wave:** 1 of 3 (startable against n2's seam; snippet assertions blocked-on-n2)
**Node:** n3
**Concurrent with:** n2 (against its seam type)
**Blocks:** n4 (areas + `UNKNOWN` verdicts), n5 (layer re-seeding at flush)

### Greenable independently?

**no — blocked by n2** for snippet-assertion tests only; stage-1
and EuRoC tests are independently greenable.

### Trunk-merge safety

**When this PR merges alone:** the new stream is additive and
publishes `UNKNOWN` areas only; existing streams untouched.
**Local dev data:** no. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `CandidateCluster`, snippet fixtures | n2 | stub/red until n2 greens | consumes the seam; does not redefine it |
| Verdicts, keypoints, snapshots | n4, n5 | absent | publishes `UNKNOWN` verdicts; snapshot oneof arm unpopulated |

**Greenable independently?** no — needs n2 green for snippet assertions (stage-1/EuRoC parts yes)

## Summary

Implements design steps 1–2: static-layer differencing into
dynamic candidate clusters, moving areas as polygons with area
tracks, published live on a new `StreamMovingAreas` RPC.

## Background

Design §1/§4: RTAB-Map gives the static world; movers are found
by differencing stereo points against an accumulated static
layer, motion-first, semantics-second.

## Scope

- Static layer (log-odds, dwell test, caps) + τ(Z, θ̂) differencing
- Areas: polygon, depth range, area tracks, live publication
- Proto + handler; unit tests + EuRoC negative control

## Technical Changes

### State A (Current)

- No moving-area pipeline; `Cm5SurveyService` has survey/detections streams only.

### State B (Target)

- `StreamMovingAreas` publishes live `MovingArea` messages keyed by `frame_id`;
  static layer persists across segments, re-seeded at flush (n5 wiring).

### Delta

- New `differencing.py` / `areas.py` / `config.py`; proto + handler additions.

## Verification

**Method:** V1-fail→pass — unit tests for layer/differencing/areas + EuRoC negative-control replay
**Command:** `uv run pytest -q tests/test_moving_differencing.py` and the EuRoC replay E2E (env-flagged)
**Before:** recorded at pass 2 with the red run
**After:** tests pass; EuRoC yields zero graduated areas; full gates green (`pytest`, `mypy`, `ruff`)
