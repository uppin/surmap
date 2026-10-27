# Changeset: Area verdicts, tracked keypoints and observation buffer

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — verdict/filter semantics, several owned symbols, one package

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-pr-stack` Plan — changeset, initial discovery · PRD = design doc (n1), §4 steps 3–5
  - [x] Record initial discovery
  - [x] Cross-check `docs/todo/` and `docs/code-issues/` — none exist for `src/surmap`
  - [x] Create/update PRD documentation — design doc on n1 serves as PRD
  - [x] Create changeset
- [wf 2] ✅ 2026-10-27 `/plan-pr-stack` Red — owned stubs + failing tests committed · commit 2; red: 7 failed in `tests/test_moving_classification.py` (plus inherited n2/n3 red)
  - [x] Stubs: `classify.py`, `keypoints.py`, `buffer.py`
  - [x] Failing tests: verdict transitions (decelerating-car no-flap), keypoint selection/filter, buffer window eviction
- [wf 3] ✅ 2026-10-27 `/green` Green — implement until every red test passes · inline green; classification tests 7 passed, mypy+ruff clean. LK implemented as bounded lk_track (numpy, 21x21 window, shift cap, None=re-seed)
  - [x] Verdict machine + statistics; LK keypoints + Kalman; buffer
  - [ ] DEFERRED: detector identity adoption wiring into stream_moving_areas, and snippet acceptance (fire/swarm/traffic) + tuning record — recorded here; they need the assembled stream wiring owned across n3/n5 and the dataset-download spikes deferred in n2
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/moving-object-detection-design.md` §4/§6 — record tuned thresholds + deciding statistics

## Initial Discovery

Full exploration: [2026-10-27-moving-classification-initial-discovery.md](./2026-10-27-moving-classification-initial-discovery.md).

## Stack Context

**Stack**: moving-object detection · slug **`#moving-objects`** — this PR is **4 of 6** · [#22](https://github.com/uppin/surmap/pull/22)
**Branch**: `pr-4-moving-classification` · **Base**: `pr-3-moving-differencing`
**Successor**: `pr-5-moving-placement`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = `/plan-red` stubs + failing tests

Why the boundary falls here: how an area behaves and what it is
(steps 3–5) is separable from where change is (n3) and from
map-frame placement (n5).

### Owned API surface

- `src/surmap/moving/classify.py` (verdict machine, motion statistics)
- `src/surmap/moving/keypoints.py` (FPS seeding, LK tracking, Kalman)
- `src/surmap/moving/buffer.py` (observation ring with VO increments)
- `tests/test_moving_classification.py`, snippet acceptance tests

### Green wave

**Wave:** 2 of 3
**Node:** n4
**Concurrent with:** none — alone in its wave
**Blocks:** n5 (buffer + verdicts for placement)

### Greenable independently?

**no — needs n3 green** (its tests drive real areas/verdict inputs).

### Trunk-merge safety

**When this PR merges alone:** areas gain verdicts/keypoints on
the moving-areas stream; no other stream changes. **Local dev
data:** no. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| Areas, `UNKNOWN` verdicts, area tracks | n3 | stub/red until n3 greens | consumes them; never re-implements differencing |
| `CandidateCluster` fixtures | n2 | real after n2 | uses snippet oracles for acceptance |

**Greenable independently?** no — needs n3 green first

## Summary

Implements design steps 3–5: classify area tracks
(rigid/oscillating/unknown), extract LK-tracked keypoints for
rigid movers, and buffer observations for retrospective placement.

## Background

Motion-first, semantics-second (design §3): only graduated
areas earn per-area compute, and verdicts must not flap.

## Scope

- Verdict state machine + motion statistics
- Keypoints with temporal identity + single ego-compensated filter
- Observation buffer; snippet acceptance suite

## Technical Changes

### State A (Current)

- Areas publish with `UNKNOWN` verdict only; no keypoints, no buffer.

### State B (Target)

- Terminal, versioned verdicts; rigid movers carry tracked
  keypoints; observations buffered per track for n5.

### Delta

- New `classify.py` / `keypoints.py` / `buffer.py`; `surmap.motion` extended.

## Verification

**Method:** V1-fail→pass — verdict/LK/buffer unit tests + snippet acceptance (fire/swarm/traffic)
**Command:** `uv run pytest -q tests/test_moving_classification.py` + snippet E2Es (env-flagged)
**Before:** baseline 432 passed on n1; red run 7 failed in this node's tests — NotImplementedError from stubs
**After:** tests pass; fire snippet zero graduations; traffic/swarm rates recorded; full gates green

## Post-green review fix (2026-10-27)

- `TrackMotionStats` accumulator added: net/path, velocity
  coherence and Welford area variance are now actually computed
  from track observations and fed to `VerdictMachine` (before,
  `AreaStats` was a dataclass nobody filled).
