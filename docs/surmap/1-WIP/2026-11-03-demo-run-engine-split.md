# Changeset: Move the demo run engine out of `demo/server.py` into `demo/runs.py`

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Refactor
**Behaviour**: preserves
**Complexity**: 3 — one package, extract-superclass plus symbol moves, facade re-export, 20+ test files import from `demo/server.py`

## Workflow

- [wf 1] ⏳ `/code-restructuring` Plan — restructure changeset, recorded baseline, `plan.jsonl` · changeset + discovery (commit 1); baseline and plan in commit 2
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation — None — Refactor, no user-visible behaviour delta
  - [x] Create changeset
  - [ ] Layout proposed, seam order fixed, snapshot taken
  - [ ] Baseline recorded (`## Baseline` Before column)
- [wf 2] ⬜ `/code-restructuring` Restructure — apply the plan, baseline still green ·
  - [ ] Dry run clean, plan applied, per-seam checks green
  - [ ] Build and full suite back to the recorded numbers
  - [ ] `uv run ruff check src tests` and `uv run mypy` clean
- [wf 3] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/surmap/changelog/2026-11-03-demo-run-engine-split.md` — write release-note file with before/after line counts and test numbers
  - [ ] `src/surmap/docs/code-issues/oversized-file-demo-server.md` — update the measured size (partial progress; issue stays open)

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-demo-run-engine-split-initial-discovery.md](./2026-11-03-demo-run-engine-split-initial-discovery.md).

State A below is distilled from that file.

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **2 of 9** · #pending
**Branch**: `pr-2-survey-agent` · **Base**: `pr-1-survey-agent`
**Successor**: `pr-3-survey-agent`
**Kind**: Refactor · behaviour-preserves
**Workflow**: preset `restructure` · planned by `/plan-pr-stack` · pass-2 = `plan.jsonl` + recorded baseline

Why the boundary falls here: the agent's `run_demo` tool (n7) must start a demo run with no HTTP
viewer attached. Today the run lifecycle lives on `_DemoHttpServer` inside a 2,215-line file; moving
it into its own module with an HTTP-free host is the seam n7 builds on, and the move must land as a
pure restructure so its baseline stays a guardrail.

### Owned API surface

- `surmap.demo.runs`: `DemoRunHost` (the run/scene state and methods extracted from
  `_DemoHttpServer`), `_RunEngine`, `_Preparation`, `TAKEOVER_TIMEOUT_S`, `_record_map`
- `surmap.demo.server` keeps re-exporting `_RunEngine` and every name tests import today

### Green wave

**Wave:** 1 of 4
**Node:** n2
**Concurrent with:** n1, n3, n4, n5, n6
**Blocks:** n7 (its demo adapter constructs a `DemoRunHost` and calls `start_run` headlessly)

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9

### Greenable independently?

**yes** — a behaviour-preserving move proven by the existing suites.

### Trunk-merge safety

**When this PR merges alone:** `scripts/demo.py`, `scripts/mission_demo.py` and `uv run pytest -q`
behave exactly as before; every import path tests and scripts use keeps resolving through the
facade. **Local dev data:** no. **Production data:** none.

## Affected Packages

- **surmap** (`src/surmap/demo`): `server.py` shrinks, `runs.py` is new.
  - `docs/viewer.md`, `docs/mission-demo.md` — no dev-doc change: neither names `_RunEngine` or the server's run methods

## Related Feature Documentation

None — behaviour-preserving restructure. No PRD.

## Summary

The run lifecycle — scene preparation, `start_run`, `start_replay`, takeover of the previous run and
the `_RunEngine` that plays, publishes and records events — moves from `demo/server.py` into
`demo/runs.py` as `DemoRunHost`, a plain class `_DemoHttpServer` now inherits from. Everything stays
reachable from `surmap.demo.server` under its current name.

## Background

`demo/server.py` is 2,215 lines against a 500-line budget
(`src/surmap/docs/code-issues/oversized-file-demo-server.md`). The agent stack needs to start and
observe runs without an HTTP request; the run engine reaches the server only through attributes
(`history_store`, `cloud_viewer`, `state_lock`, `run_lock`, `run_engine`, `current`), which is the
seam: those attributes and the methods using them form `DemoRunHost`.

## Scope

- **Plan**: layout proposed, seam order fixed, snapshot taken
- **Apply**: dry run clean, plan applied, per-seam checks green
- **Baseline**: full suite back to the recorded numbers
- **Code Quality**: `uv run ruff check src tests` and `uv run mypy` clean
- **Documentation**: the Wrap row's TODOs executed at wrap

## Technical Changes

### State A

| File | Lines | Symbols that move |
|---|---|---|
| `src/surmap/demo/server.py` | 2215 | `_Preparation` (1293), `TAKEOVER_TIMEOUT_S` (1302), `_DemoHttpServer` run/scene attributes and `start_run` (1326), `start_replay` (1363), `_take_over` (1396), `prepared_scene`, `sam_prompt`, `scene_listing`, `prepare`, `_prepare` (≈1420–1495), `_RunEngine` (1680–1863), `_record_map` (2193) |

### State B

| Module | Symbols | Projected lines | Crossing edges |
|---|---|---|---|
| `demo/runs.py` | `DemoRunHost`, `_RunEngine`, `_Preparation`, `TAKEOVER_TIMEOUT_S`, `_record_map` | ~420 | → `demo.history`, `demo.datasets`, `demo.replay`, `demo.sam_journal`, `demo.server.DemoPlayer` (lazy, see Decisions) |
| `demo/server.py` | `_DemoHttpServer(ThreadingHTTPServer, DemoRunHost)`, handler, player, rendering | ~1800 | → `demo.runs` |

### Delta — seams in dependency order

1. `_Preparation`, `TAKEOVER_TIMEOUT_S`, `_record_map` — `move_symbol` → `demo/runs.py`
2. `_RunEngine` — `move_symbol` → `demo/runs.py`; `server.py` re-exports it
3. `DemoRunHost` — extract the run/scene attributes and the eight methods from `_DemoHttpServer`
   into a base class in `demo/runs.py`; `_DemoHttpServer` inherits it

## Callers

| | |
|---|---|
| External importers | `tests/test_demo_controls.py:301` (`_RunEngine`), `tests/test_sam31_mps.py:246` (`_DemoHttpServer`) and ~20 test files importing public names from `surmap.demo.server` |
| Facade | `from surmap.demo.runs import _RunEngine` kept in `server.py` (re-export) |
| Consequence | no caller changes |

## Verification

**Method:** V2 — the recorded baseline below must still hold after the apply; nothing observable
changed.
**Command:** `uv run pytest -q && uv run mypy && uv run ruff check src tests`
**Before / After:** the `## Baseline` table.

**Covers what moves?** `tests/test_demo.py` (server start, `/stream` run lifecycle, `/datasets`,
`/prepare`), `tests/test_demo_controls.py` (`_RunEngine` subscribe/stop/takeover, pause/resume),
`tests/test_demo_replay.py` and `tests/test_demo_replay_sam.py` (`start_replay`, `record`),
`tests/test_demo_history.py` (`_record` / `_record_map` persistence), `tests/test_demo_cached_reruns.py`
(`sam_from` rebuild). Commit 2 checks the takeover-timeout path (`_take_over` returning None) is
covered; if not, a characterisation test for it is written first (V1).

## Baseline

Recorded in commit 2, before any change:

| Gate | Before | After |
|---|---|---|
| `uv run pytest -q` | | |
| `uv run mypy` | | |
| `uv run ruff check src tests` | | |

## Code Issues Closed

| Issue | Disposition |
|---|---|
| `oversized-file-demo-server.md` | Partially addressed — ~2215 → ~1800 lines; stays open for the display / floor-plan / HTTP splits it proposes |
| `oversized-file-demo-page.md` | Not touched — different file |

## Plan

`src/surmap/demo/restructure/2026-11-03-demo-run-engine-split/plan.jsonl` — written in commit 2.

## Decisions & Trade-offs

- **Extract-superclass, not composition.** A `DemoRunHost` base keeps every `self.start_run(...)`
  call site in the handler unchanged; composition (`server.runs.start_run`) would rewrite every
  handler line that touches a run, which is behaviour-neutral churn this node does not need.
- **`DemoPlayer` stays in `server.py`.** `start_run` constructs it; `runs.py` imports it lazily
  inside the method to avoid a cycle. Moving the player is part of the code issue's larger split,
  not this seam.
- **Names keep their leading underscore** — a pure move; renaming is a separate change.
