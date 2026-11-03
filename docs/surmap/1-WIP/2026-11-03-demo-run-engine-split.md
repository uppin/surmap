# Changeset: Move the demo run engine out of `demo/server.py` into `demo/runs.py`

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Refactor
**Behaviour**: preserves
**Complexity**: 3 — one package, extract-superclass plus symbol moves, facade re-export, 20+ test files import from `demo/server.py`

## Workflow

- [wf 1] ✅ 2026-11-03 `/code-restructuring` Plan — restructure changeset, recorded baseline, `plan.jsonl` · baseline 1344 passed + plan.jsonl — commit 2 (changeset + discovery @ 5602421)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation — None — Refactor, no user-visible behaviour delta
  - [x] Create changeset
  - [x] Layout proposed, seam order fixed, snapshot taken
  - [x] Baseline recorded (`## Baseline` Before column)
  - [x] Coverage of the moved code checked — 4 characterisation tests (V1) in `tests/test_demo_runs.py`
- [wf 2] ✅ 2026-11-03 `/code-restructuring` Restructure — apply the plan, baseline still green · no `restructure` executor in this checkout: the plan's six ops ran through rope, then the manual `DemoRunHost` step and plan 2 (see `## Decisions & Trade-offs`); full suite 1321 passed · 32 Known-red · 30 skipped, same as before the apply in this checkout; mypy and ruff clean — apply commit (the `refactor(demo): apply the run engine split` commit)
  - [x] Dry run clean, plan applied, per-seam checks green — the executor's dry run was not available, so each op's rope change set was computed before it was written; per-seam, each seam's moved members were checked verbatim (AST) after plan 1 and after the cut; the gates ran once after the final seam, not after each one
  - [x] Build and full suite back to the recorded numbers — see `## Baseline` After column (1383 collected in both; 23 fixture-gated e2e tests skip in this checkout)
  - [x] `uv run ruff check src tests` and `uv run mypy` clean
- [wf 3] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/surmap/changelog/2026-11-03-demo-run-engine-split.md` — write release-note file with before/after line counts and test numbers
  - [ ] `src/surmap/docs/code-issues/oversized-file-demo-server.md` — update the measured size (partial progress; issue stays open)

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-demo-run-engine-split-initial-discovery.md](./2026-11-03-demo-run-engine-split-initial-discovery.md).

State A below is distilled from that file.

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **2 of 9** · [#77](https://github.com/uppin/surmap/pull/77)
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
  `_DemoHttpServer`), `_RunEngine`, `PlaybackControls`, `_Preparation`, `TAKEOVER_TIMEOUT_S`,
  `_record_map`
- `surmap.demo.server` keeps re-exporting `_RunEngine`, `PlaybackControls`, `TAKEOVER_TIMEOUT_S`
  and `DemoRunHost` (`X as X`, so the old paths resolve under mypy strict too)

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

## Inherited Dependencies — do not implement here

| Predecessor | Owns | Used here |
|---|---|---|
| n1 (#76, `pr-1-survey-agent`) | `surmap.agent.*` — tool/chat protos, `contracts.py`, `services.py` (stubs until n1's `/green`) | none — this node neither imports nor touches `surmap.agent`; n1's 32 red tests are inherited Known-red only (`## Baseline`) |

**Greenable independently?** yes

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
| `src/surmap/demo/server.py` | 2215 | `PlaybackControls` (853–916, 64 lines), `_Preparation` (1293–1299, 8), `TAKEOVER_TIMEOUT_S` (1302), `_DemoHttpServer` run/scene attribute annotations (1307–1324) and `start_run` (1326), `start_replay` (1363), `_take_over` (1396), `prepared_scene` (1420), `sam_prompt` (1430), `scene_listing` (1436), `prepare` (1467), `_prepare` (1480–1494) — 189 lines, `_RunEngine` (1680–1862, 183), `_record_map` (2193–2210, 18) |

464 lines move in all.

### State B

| Module | Symbols | Projected lines | Crossing edges |
|---|---|---|---|
| `demo/runs.py` | `DemoRunHost`, `_RunEngine`, `PlaybackControls`, `_Preparation`, `TAKEOVER_TIMEOUT_S`, `_record_map` | ~505 (464 moved + imports) — at the 500 budget | → `demo.history`, `demo.datasets`, `demo.events`, `demo.replay`, `demo.sam_journal`, `demo.sam_prompt`, `demo.cloud_view`, `demo.surface_render`, `demo.surface_timeline`; → `demo.server.DemoPlayer` **only lazily**, inside `start_run`'s `play` (see Decisions) |
| `demo/server.py` | `_DemoHttpServer(ThreadingHTTPServer, DemoRunHost)` (body: `daemon_threads = True`), handler, `DemoPlayer`, workers, rendering, `make_demo_server` | ~1755 | → `demo.runs` (module level) |

No module-level import cycle: `server` → `runs` at import time; `runs` → `server` only at call
time, for `DemoPlayer`.

### Delta — seams in dependency order

1. **Leaves** — `_Preparation`, `TAKEOVER_TIMEOUT_S`, `PlaybackControls`, `_record_map`:
   `move_symbol` → `demo/runs.py` (plan ops 1–4). Nothing they reference lives in `server.py`, so
   `runs.py` imports nothing from `server` and the tree is green after this seam.
2. **`_RunEngine`** — `move_symbol` → `demo/runs.py` (plan op 5), then `organize_imports` on
   `server.py` (op 6). rope authors `from surmap.demo.server import _DemoHttpServer` into `runs.py`
   for the `server:` annotation, which is a module-level cycle; seam 3 removes it, so seams 2 and 3
   are gated together.
3. **`DemoRunHost`** — extract-superclass, which no Python operation expresses (Decisions): the
   manual step below, then a second plan of import passes, then the facade lines.

#### Manual step — extract `DemoRunHost` (after `plan.jsonl` is applied)

Cut and paste only; no line of a moved body is retyped. Against the tree plan 1 leaves:

1. In `demo/runs.py`, append `class DemoRunHost:` with a one-line docstring — *The demo's runs
   and scenes, with no HTTP attached; `_DemoHttpServer` serves it.*
2. **Cut** from `_DemoHttpServer` into it, verbatim and in order: the 18 attribute annotations
   (`catalog` … `history_store`, today 1307–1324) and the eight methods `start_run`,
   `start_replay`, `_take_over`, `prepared_scene`, `sam_prompt`, `scene_listing`, `prepare`,
   `_prepare` (today 1326–1494). `daemon_threads = True` stays in `_DemoHttpServer`.
3. In `server.py`, change the header to `class _DemoHttpServer(ThreadingHTTPServer, DemoRunHost):`;
   its body is `daemon_threads = True` alone.
4. In `DemoRunHost.start_run`'s nested `play`, add `from surmap.demo.server import DemoPlayer` as
   its first statement (the one lazy import; `DemoPlayer` stays in `server.py`).
5. In `runs.py`, change `_RunEngine.__init__`'s `server: _DemoHttpServer` to `server: DemoRunHost`
   and delete rope's `from surmap.demo.server import _DemoHttpServer`. `_RunEngine` reads only
   `cloud_viewer`, `history_store`, `state_lock`, `run_engine`, `current` — all `DemoRunHost`
   attributes.
6. Plan 2, written then against that tree (fresh snapshot): `add_missing_imports` on `runs.py`,
   `organize_imports` on `runs.py` and `server.py`.
7. Last, by hand (an import pass would strip them as unused): the facade in `server.py` —
   `from surmap.demo.runs import TAKEOVER_TIMEOUT_S as TAKEOVER_TIMEOUT_S`,
   `PlaybackControls as PlaybackControls`, `_RunEngine as _RunEngine`, and `DemoRunHost` (used by
   the class header). The existing `# type: ignore[arg-type]` in `start_run` moves with its line;
   no new suppression is added.
8. Gate: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy && uv run pytest -q`.

## Callers

| | |
|---|---|
| Importers of `surmap.demo.server` | 21 files — 19 test files and `scripts/demo.py`, `scripts/viewer.py` |
| Importers of a **moved** name | 5 test files: `tests/test_demo_controls.py` (`PlaybackControls`; `_RunEngine` at :301), `tests/test_demo_cloud_ptz.py`, `tests/test_demo_cloud_follow.py`, `tests/test_demo_surfaces.py` (`PlaybackControls`), `tests/test_demo_runs.py` (`_RunEngine`, `PlaybackControls`, `TAKEOVER_TIMEOUT_S`) |
| `src` importers of a moved name | none (`demo/replay.py` and `demo/cloud_view.py` name `PlaybackControls` only in prose) |
| Monkeypatches of a moved name | none — no test patches `TAKEOVER_TIMEOUT_S` or any moved symbol through `surmap.demo.server` |
| Facade | `X as X` re-exports in `server.py` for `_RunEngine`, `PlaybackControls`, `TAKEOVER_TIMEOUT_S` (manual step 7) — permanent: n7 and out-of-tree callers keep the old path |
| Consequence | the 5 test files' import lines name `surmap.demo.runs` (option 1). **Observed in the apply:** rope did not rewrite them, so they were edited by hand (import lines only); every other caller is untouched, and the facade keeps every old path resolving |
| Re-exports the plan did not list | `server.py`'s explicit `X as X` re-exports of `CloudPose`, `render_cloud_view`, `CLOUD_VIEW_PX`, `MOVING_ALPHA`, `MOVING_COLOUR`, `SURFACE_ALPHA`, `SURFACE_COLOURS`, `surface_tint` are imported by `tests/test_demo.py` and `tests/test_demo_surfaces.py`. Plan 2's `organize_imports` on `server.py` dropped them as unused; restored by hand (see Decisions) |

## Verification

**Method:** V2 — the recorded baseline below must still hold after the apply; nothing observable
changed.
**Command:** `uv run pytest -q && uv run mypy && uv run ruff check src tests`
**Before / After:** the `## Baseline` table.

**Covers what moves?** `tests/test_demo.py` (server start, `/stream` run lifecycle, `/datasets`,
`/prepare`), `tests/test_demo_controls.py` (`_RunEngine` subscribe/stop/takeover, pause/resume),
`tests/test_demo_replay.py` and `tests/test_demo_replay_sam.py` (`start_replay`, `record`),
`tests/test_demo_history.py` (`_record` / `_record_map` persistence), `tests/test_demo_cached_reruns.py`
(`sam_from` rebuild), plus `tests/test_demo_cloud_ptz.py` / `test_demo_cloud_follow.py` /
`test_demo_surfaces.py` (`PlaybackControls`).

**Coverage measured in commit 2** (`coverage run` over the demo suites, `--include` the target):
the takeover timeout (`_take_over` returning None), a run finishing before it is registered, a
playback that raises, and a failed preparation were **not executed** by any test. Characterisation
tests (V1, green now, fluent Given/When/Then) were written for them in a new suite named after the
target module — `tests/test_demo_runs.py`:

| Test | Path it pins |
|---|---|
| `tests/test_demo_runs.py:88` `test_a_new_run_is_refused_while_the_current_run_will_not_stop` | `_take_over` → None after waiting `TAKEOVER_TIMEOUT_S`; the stuck run stays current |
| `tests/test_demo_runs.py:104` `test_a_run_over_before_it_is_registered_leaves_nothing_playing` | `_take_over`'s unregister-again branch |
| `tests/test_demo_runs.py:115` `test_a_run_whose_playback_breaks_is_persisted_as_interrupted` | `_RunEngine._play`'s `except Exception` → `interrupted` |
| `tests/test_demo_runs.py:129` `test_a_scene_whose_download_fails_is_listed_as_failed_with_the_reason` | `_prepare`'s error state, surfaced by `scene_listing` |

Still unexecuted inside moved symbols, left so deliberately: `prepare`'s early returns,
`_RunEngine`'s `record=False` guard, `subscribe` on a finished run, `_offer`'s full-queue drop and
`_record`'s `detections` branch. Each moves inside a whole symbol, untouched, so the only way the
move can break it is name resolution — which `mypy` strict checks over every line.

## Baseline

Recorded in commit 2, before any change:

| Gate | Before | After |
|---|---|---|
| `uv run pytest -q` | 1344 passed · 32 failed (all Known-red, below) · 7 skipped — 1340 passed before the 4 characterisation tests | 1321 passed · 32 failed (the same 32 Known-red, each `NotImplementedError` from n1's stubs) · 30 skipped — 1383 collected both times. The checkout the Before row was taken on had the generated fixtures (`tests/fixtures/euroc_v101_rtabmap`, `coral_model`), so its e2e tests ran; this worktree lacks them and 23 of them skip. Measured before the apply in this checkout: 1321 / 32 / 30 (one run also hit the load-sensitive `test_differencing_is_within_frame_budget`, which passes alone). The skip list and the 32 failures match the before run |
| `uv run mypy` | Success: no issues found in 316 source files | Success: no issues found in 317 source files (`demo/runs.py` is the new file) |
| `uv run ruff check src tests` | All checks passed | All checks passed |
| `uv run ruff format --check src tests` | 341 files already formatted | 342 files already formatted |

Two of five full runs also failed `tests/test_moving_differencing.py::test_differencing_is_within_frame_budget`
(a wall-clock budget, no demo code) while the host's load average was ~40 from parallel agents; it
passed in isolation 3/3 and on the other runs. A flake under load, not part of the baseline — if it recurs after the apply, re-run it alone before
attributing it to the move.

### Known-red

Inherited from n1 (`pr-1-survey-agent`, commit 2): its planned red tests, each failing with
`NotImplementedError` from n1's stubs. They must still fail, for that same reason, after the apply.

| Suite | Tests | Fails at |
|---|---|---|
| `tests/test_agent_contracts.py` | 23 — every test in the file (`test_every_survey_tools_rpc_is_a_tool_named_in_snake_case` … `test_a_service_whose_rpcs_declare_no_default_execution_has_no_tool_contracts`) | `src/surmap/agent/contracts.py:75` |
| `tests/test_agent_services.py` | 9 — every test in the file (`test_the_survey_tools_module_mounts_on_an_in_memory_host` … `test_a_handler_for_an_rpc_the_service_lacks_fails_at_mount`) | `src/surmap/agent/services.py:23`, `:28`, `:33` |

## Code Issues Closed

| Issue | Disposition |
|---|---|
| `oversized-file-demo-server.md` | Partially addressed — 2215 → 1750 lines in `server.py` (+ 504-line `runs.py`); stays open for the display / floor-plan / HTTP splits it proposes. Not deleted |
| `oversized-file-demo-page.md` | Not touched — different file |

## Plan

Applied in the Restructure row. Plan 1 was 6 operations (5 `move_symbol` → `src/surmap/demo/runs.py`,
1 `organize_imports`) against snapshot `server.py` @ `sha256:def7fbc9…a85a1`; the manual `DemoRunHost`
step (18 annotations and 8 methods cut verbatim, one lazy import, one annotation, the header base) and
plan 2 (12 `add_missing_imports` intents on `runs.py`, `organize_imports` on `runs.py` and `server.py`)
followed it, then the facade lines by hand. The `plan.jsonl` file was deleted in the apply commit
(`git ls-files '*/restructure/*/plan.jsonl'` prints nothing).

## Decisions & Trade-offs

- **Extract-superclass, not composition.** A `DemoRunHost` base keeps every `self.start_run(...)`
  call site in the handler unchanged; composition (`server.runs.start_run`) would rewrite every
  handler line that touches a run, which is behaviour-neutral churn this node does not need.
- **`DemoPlayer` stays in `server.py`.** `start_run` constructs it; `runs.py` imports it lazily
  inside the method to avoid a cycle. Moving the player is part of the code issue's larger split,
  not this seam.
- **Names keep their leading underscore** — a pure move; renaming is a separate change.
- **The vocabulary cannot express extract-superclass in Python.** `extract_class` is TypeScript-only
  (and builds a delegate, not a base class); Python has `move_symbol` for whole module-level
  symbols, not class members. The `DemoRunHost` step is therefore a cut-and-paste of whole members
  (`### Delta` → *Manual step*), bracketed by engine-backed moves and import passes. The members
  move verbatim; the only hand-typed tokens are the class header, the base-class list, one lazy
  import, one annotation (`_DemoHttpServer` → `DemoRunHost`) and the facade lines.
- **`PlaybackControls` moves too** (beyond the original surface). `_RunEngine.__init__` constructs
  it, so leaving it in `server.py` would make `runs.py` import `server` at module level — a cycle.
  It is a leaf (threading + `CloudViewer`), it is the run's control state (`current`), and moving it
  costs 4 test files one import line each, kept old-path-reachable by the facade.
- **Importers are rewritten, and the facade is kept anyway.** The plan expected rope to rewrite the
  5 test files' imports; it did not (rope saw no occurrence through `surmap.demo.server`). They were
  edited by hand to `surmap.demo.runs`, and the `X as X` facade is kept so `surmap.demo.server` stays a
  complete surface for n7 and scripts.
- **The `restructure` executor is not in this checkout** (`common/code-restructuring/` is absent), so
  nothing ran `restructure check`, `--dry-run`, `status` or `verify`. The six plan-1 intents were
  applied by a rope script (`rope` 1.15.0, driven directly, not the plan executor): each anchor was
  resolved to its name against the snapshot (`git show HEAD:…`) and each move was computed as a rope
  change set before it was written. The executor's own journal and anchor ledger were not exercised.
- **rope's stock `add_import` writes `runs.X` into `server.py`.** The existing `from surmap.demo import
  run_archive` line makes rope merge into it and qualify every moved reference (`runs.PlaybackControls`),
  which would have put a `runs.` self-import into `runs.py` and changed the moved bodies. The apply
  pins the import style to bare `from surmap.demo.runs import X` (`from-global`, and a patched
  `add_import` that always takes the `from` form). Verified: each moved top-level symbol and each
  `DemoRunHost` member is AST-identical to its `HEAD` source, and `start_run` differs only by the lazy
  import.
- **plan 2's `organize_imports` removed re-exports the plan did not foresee.** `server.py` no longer
  uses `CloudPose`, `render_cloud_view`, `MOVING_*`, `SURFACE_*`, `surface_tint` or `CLOUD_VIEW_PX`,
  so organize dropped their `X as X` lines, and `tests/test_demo.py` and `tests/test_demo_surfaces.py`
  failed at mypy and import. They were restored as explicit `X as X` re-exports, and the other
  unused imports that organize removed (`PrepareProgress`, `JournalPlayer`, `ensure_dataset` and
  similar) have no importer in `src`, `tests`, `scripts`, `examples` or `deploy`.
- **Ruff isort (`I001`) reordered the two modules and the test imports** after the rope passes, which
  left the moved names in unsorted, sometimes combined statements. Import order only.
- **Decided without review (apply):** the 5 test-file import lines (`surmap.demo.runs`); the 8
  restored re-exports in `server.py`; the rope import-style pin (above); the ruff import-order fixes;
  `runs.py` at 504 lines against the 500-line budget (planned ~505). Nothing else was deleted.
- **Dead code: none removed.** `code-analysis` is not installed; the measured coverage found no
  unreachable moved member — every uncovered line is a reachable branch (`## Verification`).
- **Characterisation tests in a new suite.** `tests/test_demo_controls.py` is 386 lines; the four
  tests (~140 lines with their helpers) would have pushed it past the 500-line oversized-test bar.
  `tests/test_demo_runs.py` is named after the module the code moves to.
