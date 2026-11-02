# Changeset: Demo run export and import

**Date**: 2026-11-02
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package; an I/O seam (file format, HTTP upload/download); store-level integration tests

## Workflow

- [wf 1] ✅ 2026-11-02 `/plan-red` Plan — PRD, changeset, initial discovery · PRD-2026-11-02-demo-run-export-import.md + this file
  - [x] Record initial discovery
  - [x] Cross-check src/surmap/docs/todo/ and src/surmap/docs/code-issues/
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7)
- [wf 2] ✅ 2026-11-02 `/plan-red` Red — acceptance and failing lower-tier tests, committed · `tests/test_demo_run_archive.py` red (module missing)
  - [x] Acceptance tests written and failing for the right reason
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ⏳ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: `demo/run_archive.py` — `export_run`, `import_runs`, the `.surmaprun` format
  - [ ] Milestone 2: `GET /runs/<id>/export`, `POST /runs/import`
  - [ ] Milestone 3: page Export / Import buttons
  - [ ] Milestone 4: CLI `python -m surmap.demo.run_archive export|import`
  - [ ] Acceptance: `tests/test_demo_run_archive.py` passes
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] README.md § Dev console — Export / Import bullet
  - [ ] docs/surmap/changelog/2026-11-02-demo-run-export-import.md — history entry
  - [ ] src/surmap/docs/code-issues/oversized-file-demo-page.md and oversized-file-demo-server.md — measurement rows
  - [ ] Validate tests (`/validate-tests`)

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-02-demo-run-export-import-initial-discovery.md).

## Prerequisites

### Code Issues

- ⚠ during: `oversized-file-demo-server.md` and `oversized-file-demo-page.md`. The archive
  logic lives in a new `demo/run_archive.py`, and the server and page gain only routes and
  two buttons.

## Affected Packages

- `surmap`:
  - new `demo/run_archive.py`;
  - `demo/server.py` (two routes);
  - `demo/page.py` (two buttons and their script).

## Summary

Export a run (and its replay source chain) to one `.surmaprun` file; import such a file
into any console's history.

## Technical Changes

### State A (Current)

Runs exist only in the console's `demo-history.db`; nothing copies a run out or in.

### State B (Target)

- **The format** (`.surmaprun`): a gzipped SQLite database with the history schema
  (`history.SCHEMA`). It holds the run and its source chain, plus
  `export_info(format_version, run_id, exported_at)`.
- **Export:** `run_archive.export_run(store_path, run_id, out)` copies the rows of every
  run in the chain, then gzips the file. A run with status `running` raises
  `RunNotExportable`.
- **Import:** `run_archive.import_runs(store_path, archive) -> ImportReport(imported,
  skipped)` gunzips to a temporary file and checks `export_info`, raising `NotARunArchive`
  if it is missing or the version is unknown. For each run not already present it copies
  the rows; AUTOINCREMENT tables are copied in id order without their ids, so they are
  renumbered in the same order. A run already present is skipped.
- **HTTP:**
  - `GET /runs/<id>/export` sends the file as an attachment
    (`surmap-<dataset>-<id8>.surmaprun`);
  - `POST /runs/import` takes the raw file, streamed to a temporary file, and answers
    `{imported, skipped}`, with 400 for a non-archive and 409 for a running run.
- **Page:** Export downloads the selected run; Import (a file picker) uploads, refreshes
  the list and selects the first imported run.
- **CLI:** `python -m surmap.demo.run_archive export RUN_ID FILE [--history-db PATH]` and
  `import FILE [--history-db PATH]`.

## Verification

**Method:** V1 fail→pass (`tests/test_demo_run_archive.py`), plus V3 on the real run
**Command:** `uv run pytest -q tests/test_demo_run_archive.py`
**Before:** the module doesn't exist; every test fails.
**After:**
- all tests pass;
- `acdcc6aa` exports, and imports into a fresh store with identical per-table row counts
  and checksums of frames and dense buffer;
- the imported run's snapshot equals the original's.

## Decisions & Trade-offs

- **SQLite in gzip, not JSON or zip.** It reuses the schema and the store, keeps blobs
  binary, and the JSON-heavy rows compress well.
- **Original `run_id`s.** They keep a run's identity across machines and make re-import
  idempotent. Two different runs never share a uuid4 id.
