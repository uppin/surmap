# Dataset runs: builds cached by key, listed and run from the gallery and the agent

**Date:** 2026-11-04
**Status:** 🚧 In Progress
**Type:** Feature
**Behaviour:** adds
**Complexity:** medium — proto contract, history schema, workspace, routes and web gallery

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + companion
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests · 12 pytest (`test_agent_dataset_runs.py`) + 1 route + 3 vitest red
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · pytest 2575 passed, vitest 162 passed
  - [x] `run_cache_keys` table and `RunHistoryStore.cached_runs`
  - [x] `run_demo` / `run_rtabmap` answer from the cached run for their key unless `rebuild`
  - [x] `list_runs` and `run_cached` tools
  - [x] Gallery: Cached badge and Runs list with preview and Run
- [wf 4] ⏳ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/agent.md` — tool tables and Dataset gallery section updated
  - [ ] Changelog entry written; this changeset and its companion deleted

## Initial Discovery

See `2026-11-04-dataset-runs-cache-initial-discovery.md`.

## State A

Every agent build of a dataset recorded a new run; only the demo console reused a cached run, and
only the newest per scene.

## State B

A build is cached by key (RTAB-Map, SAM prompt, on-board model, frame limit). An identical
`run_demo` / `run_rtabmap` answers from that key's cached run (`cached: true`) unless
`rebuild: true`. `list_runs` lists a dataset's runs, one per key; `run_cached` answers from one.
Gallery cards show a Cached badge and a Runs list with a preview frame and a Run button.

## Delta

Proto: `CachedRun`, `ListRuns`, `RunCached`, `rebuild`, `RunInfo.cached`,
`RunDemoResponse.cached`, `DatasetEntry.runs`. History: `run_cache_keys`, `cached_runs`.
`GET /datasets` carries `runs`.

## Verification

V1 — executable tests: `tests/test_agent_dataset_runs.py`,
`tests/test_agent_dataset_thumbnail_route.py`, `DatasetGallery.test.tsx`; plus every gate.
