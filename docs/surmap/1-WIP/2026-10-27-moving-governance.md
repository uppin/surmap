# Changeset: Moving-area resource budgets and CM5 profile gate

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Infra
**Behaviour**: preserves
**Complexity**: 3 — counters/caps around existing stages, recorded measurement, one package

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-pr-stack` Plan — changeset, initial discovery · this file + companion
  - [x] Record initial discovery
  - [x] Cross-check `docs/todo/` and `docs/code-issues/` — none exist for `src/surmap`
  - [x] Create/update PRD documentation — None — Infra, no user-visible behaviour delta; design §5 governs
  - [x] Create changeset
- [wf 2] ✅ 2026-10-27 `/plan-pr-stack` Guardrail — failing governance tests + recorded baseline · commit 2; full-suite state on this branch: 434 passed / 24 failed, all 24 being the stack's recorded red tests (n2:4, n3:7, n4:7, n5:3, n6:3)
  - [x] Stub: `governance.py` (counters, caps, degradation ladder)
  - [x] Failing tests in `tests/test_moving_governance.py`; baseline test counts recorded
- [wf 3] ✅ 2026-10-27 `/green` Green — implement until every red test passes · inline green; governance tests 3 passed; FULL stack-tip suite 458 passed, mypy+ruff clean
  - [x] BudgetGovernor counters/caps/ladder implemented (producers are the n3-n5 stage APIs; governor aggregates their counters)
  - [ ] DEFERRED: CM5-profile replay (EuRoC + KITTI, sidecar active) with recorded budget table — blocked on the handler-level integration deferred in n4/n5 (assembled pipeline in the stream handler); recorded here, before this feature is enabled by default on-board
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/moving-object-detection-design.md` §2/§5 — record measured budgets

## Initial Discovery

Full exploration: [2026-10-27-moving-governance-initial-discovery.md](./2026-10-27-moving-governance-initial-discovery.md).

## Stack Context

**Stack**: moving-object detection · slug **`#moving-objects`** — this PR is **6 of 6** · [#24](https://github.com/uppin/surmap/pull/24)
**Branch**: `pr-6-moving-governance` · **Base**: `pr-5-moving-placement`
**Successor**: none — top of stack
**Kind**: Infra · behaviour-preserves
**Workflow**: preset `infra` · planned by `/plan-pr-stack` · pass-2 = failing governance tests + recorded baseline

Why the boundary falls here: budgets are only measurable on
the assembled pipeline, so governance closes the stack.

### Owned API surface

- `src/surmap/moving/governance.py` (counters, caps, degradation ladder)
- CM5-profile replay harness (env-flagged E2E)
- `tests/test_moving_governance.py`

### Green wave

**Wave:** 3 of 3
**Node:** n6
**Concurrent with:** n5
**Blocks:** nothing

### Greenable independently?

**no — needs n5 green** (it measures the assembled pipeline).

### Trunk-merge safety

**When this PR merges alone:** budgets enforced on an already
working feature; degradation only under over-budget pressure.
**Local dev data:** no. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| Stage counters' producers | n3, n4, n5 | real after those nodes | aggregates/enforces; never re-instruments their stages |

**Greenable independently?** no — needs n5 green first

## Summary

Enforces design §5 budgets on the assembled moving-object
pipeline and proves them in a CM5-profile replay.

## Background

RTAB-Map is the primary product; this feature is a tenant
(design §5). Budgets must be enforced, not hoped for.

## Scope

- Per-stage counters, hard caps, degradation ladder
- Layer-memory enforcement; CM5-profile budget gate

## Technical Changes

### State A (Current)

- Stages run uncapped (beyond per-node internal limits); no budget evidence.

### State B (Target)

- Counters published, caps enforced, ladder degrades the
  feature (never RTAB-Map) under sustained over-budget.

### Delta

- New `governance.py`; replay harness; recorded budget table.

## Verification

**Method:** V3 — deterministic CM5-profile replay with recorded before/after budget counters (plus V1 unit tests for caps/ladder)
**Command:** `uv run pytest -q tests/test_moving_governance.py` + CM5-profile replay E2E (env-flagged)
**Before:** baseline on n1: 432 passed; on this branch 434 passed / 24 failed (the stack's red tests, itemized in wf 2)
**After:** budgets in design §2 hold for full EuRoC + KITTI replay; full gates green
