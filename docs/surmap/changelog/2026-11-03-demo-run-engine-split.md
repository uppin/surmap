# `demo/server.py` 2215 ➜ 1750 lines — the run engine moves to `demo/runs.py`

**Date:** 2026-11-03
**Type:** Refactor
**Packages:** surmap

The demo's runs and scenes no longer live inside the HTTP server module. `src/surmap/demo/runs.py`
(440 lines) now holds `DemoRunHost` (start, replay and takeover of runs, scene preparation and
listing, with no HTTP attached), `_RunEngine`, `_Preparation`, `TAKEOVER_TIMEOUT_S` and `_record_map`;
`src/surmap/demo/playback.py` (71 lines) holds `PlaybackControls`. `_DemoHttpServer` is now
`ThreadingHTTPServer` plus `DemoRunHost` with `daemon_threads = True` as its whole body, so an
agent-facing caller can drive runs without a socket. `server.py` re-exports `TAKEOVER_TIMEOUT_S`,
`PlaybackControls` and `_RunEngine`, and `runs.py` re-exports `PlaybackControls`, so every existing
import keeps working. The one new edge is lazy: `DemoRunHost.start_run` imports `DemoPlayer` from
`server` at call time, which keeps `server` → `runs` the only import-time dependency. Moved bodies
were cut and pasted, not retyped.

Not moved: `DemoPlayer`, the workers, floor-plan rendering and the HTTP handler stay in `server.py`
(still 1750 lines; the split it needs stays tracked in
`src/surmap/docs/code-issues/oversized-file-demo-server.md`).

Behaviour unchanged: 1353 passed · 30 skipped with the predecessor's tests green (1344 passed before
the move on a checkout that had the generated fixtures; 23 fixture-gated tests skip here), plus 4
characterisation tests for takeover timeout, run finished before registration, a playback that
raises and a failed download (`tests/test_demo_runs.py`). `mypy` strict (318 files) and
`ruff check` / `ruff format --check` are clean, with no new suppression.
