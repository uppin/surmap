# Dataset builds cached by key, listed as Runs and run again from the cache

**Date:** 2026-11-04
**Feature:** Survey agent / dataset gallery

- **Cache key.** `run_demo` and `run_rtabmap` cached each build by its key: RTAB-Map, the SAM
  concept, the on-board model and the frame limit (`rtabmap+sam=car;frames=200`). The key was
  stored per run in the history's new `run_cache_keys` table; a key's cached run was its newest
  complete, journalled, non-replay run, holding that build's RTAB-Map map, dense depth and SAM
  results.
- **Reuse.** An identical request answered from the key's cached run, marked `cached`, and
  recorded nothing; `rebuild: true` recorded a new run that became the key's cached run.
- **Runs.** Each dataset kept one cached run per key. `list_runs` listed them, newest first, with
  a preview frame; `run_cached` answered from one without RTAB-Map or SAM. `DatasetEntry.runs`
  and `GET /datasets` carried them.
- **Gallery.** A built dataset's card was badged **Cached** and listed its **Runs**, each with a
  preview of its first recorded frame and a Run button that asked the agent to use `run_cached`.
- **Not cached.** `run_sam_on_dataset` records no run. Run archives do not carry cache keys, so
  an archive exported before this change still imports.
- **Code.** `RunHistoryStore.record_cache_key` / `cached_runs`, `CachedRecording`,
  `workspace.cache_key`, `DemoWorkspace.cached_runs` / `run_cached`, `dataset_handlers.list_runs`
  / `run_cached`, `DatasetGallery`'s `DatasetRuns`.
- **Tests.** pytest: 12 dataset-run, 1 gallery-route; vitest: 3 gallery. Full suite 2575 passed,
  38 skipped; web 162 passed; ruff, ruff format and strict mypy clean.

Docs: [docs/agent.md](../../agent.md) (*Dataset gallery* — Runs).
