# Changeset: Real-video snippet fixtures and candidate seam

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Infra
**Behaviour**: preserves
**Complexity**: 3 — fetch/conversion adapters and integration tests, one package, no behaviour change

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-pr-stack` Plan — changeset, initial discovery · this file + companion
  - [x] Record initial discovery
  - [x] Cross-check `docs/todo/` and `docs/code-issues/` — none exist for `src/surmap` (recorded in discovery)
  - [x] Create/update PRD documentation — None — Infra, no user-visible behaviour delta; the design doc (n1) is the governing document
  - [x] Create changeset
- [wf 2] ✅ 2026-10-27 `/plan-pr-stack` Guardrail — failing fixture/seam tests committed · commit 2; baseline 432 passed (`uv run pytest -q`), red: 4 failed / 2 passed in `tests/test_moving_snippets.py` (stubs raise NotImplementedError)
  - [x] `CandidateCluster` seam type + stub snippet registry/oracle loaders
  - [x] Failing tests in `tests/test_moving_snippets.py` (registry contents, oracle converters, calib→sensor.yaml)
- [wf 3] ✅ 2026-10-27 `/green` Green — implement until every red test passes · inline green; `tests/test_moving_snippets.py` 6 passed; KITTI range-extraction verified live against avg-kitti S3 (calib zip index + member extract, seq 0020 baseline 0.5323 m)
  - [x] `scripts/fetch_moving_snippets.py` (pinned fetch, KITTI range-extraction, COLMAP cross-check command)
  - [x] Snippet registry + oracle converters (VisDrone MOT, Purdue refined_gt, KITTI calib→sensor.yaml)
  - [x] KITTI EuRoC-layout staging converter (sensor.yaml; image staging is fetch-script extraction)
  - [ ] DEFERRED spikes (recorded, non-blocking for this node's tests): Boreal fetch vs Wennington fallback, VisDrone sequence pick, Purdue window pick, Byrne camera motion, COLMAP fx run — dataset downloads to be done with the n3/n4 snippet E2Es that consume them
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/moving-object-detection-design.md` §6.1/§6.2 — fold snippet outcomes into the design's evaluation record

## Initial Discovery

Full exploration: [2026-10-27-moving-snippets-initial-discovery.md](./2026-10-27-moving-snippets-initial-discovery.md).
State A below is distilled from it.

## Stack Context

**Stack**: moving-object detection · slug **`#moving-objects`** — this PR is **2 of 6** · [#19](https://github.com/uppin/surmap/pull/19)
**Branch**: `pr-2-moving-snippets` · **Base**: `docs/moving-object-design` (n1, #17)
**Successor**: `pr-3-moving-differencing`
**Kind**: Infra · behaviour-preserves
**Workflow**: preset `infra` · planned by `/plan-pr-stack` · pass-2 = failing fixture tests + recorded baseline

Why the boundary falls here: every later node asserts against these
fixtures; the seam type must exist before differencing can be
specified against it.

### Owned API surface

- `scripts/fetch_moving_snippets.py`
- `src/surmap/moving/__init__.py`, `src/surmap/moving/candidates.py` (`CandidateCluster`)
- `src/surmap/moving/snippets.py` (registry, oracle loaders/converters, KITTI staging)
- `tests/test_moving_snippets.py`

### Green wave

**Wave:** 1 of 3
**Node:** n2
**Concurrent with:** n1 (#17)
**Blocks:** n3 (its snippet stage-2 assertions), n4 (snippet acceptance), n5 (KITTI stereo E2E)

Real dependency edges: n1 → n2 → n3 → n4 → n5 → n6 (branch line);
n2's fixtures are also consumed directly by n4 and n5 tests.

### Greenable independently?

**yes** — it owns everything its tests drive.

### Trunk-merge safety

**When this PR merges alone:** production and local dev workflows
unchanged (fixtures + seam types only). **Local dev data:** no.
**Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| Design + evaluation programme | n1 (#17) | merged/landing below | implements its §6.1/§6.2 fixture requirements; does not re-decide them |

**Greenable independently?** yes

## Summary

Adds the snippet fetch/registry/oracle tooling and the
`CandidateCluster` seam type the moving-object pipeline is
specified and tested against.

## Background

Design §6 requires real-video snippet controls plus one
stereo+calibration KITTI snippet; today the repo has only the
EuRoC demo dataset registry (`src/surmap/demo/datasets.py`),
which is EuRoC-format only.

## Scope

- Snippet fetch script with pinned URLs/hashes and KITTI range-extraction
- Snippet registry and oracle converters for traffic/fire/swarm/KITTI
- `CandidateCluster` seam type; failing-then-passing fixture tests

## Technical Changes

### State A (Current)

- Only EuRoC demo data exists; no snippet fixtures, no candidate seam type.

### State B (Target)

- Four snippet fixtures fetchable and convertible offline-after-fetch;
  oracle annotations load into typed clusters; KITTI stages into EuRoC layout.

### Delta

- New `src/surmap/moving/` package (seam + snippets), fetch script, tests.

## Verification

**Method:** V1-fail→pass — failing fixture tests (registry, converters, calib conversion), committed red, green at implementation
**Command:** `uv run pytest -q tests/test_moving_snippets.py`
**Before:** baseline 432 passed (2026-10-27, pass 2); red run 4 failed / 2 passed — failures are NotImplementedError from the n2 stubs
**After:** all snippet tests pass; `uv run pytest -q`, `uv run mypy`, `uv run ruff check src tests` green
