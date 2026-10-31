# Changeset: Generic test console — persisted runs, history scrub, 3D point cloud

**Date**: 2026-10-31
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — one package but HTTP/SSE contract change, SQLite I/O seam, concurrency (stream thread writes, request threads read), browser 3D viewer

## Workflow

- [wf 1] ✅ 2026-10-31 `/plan-red` Plan — changeset, initial discovery · this file + companion discovery
- [wf 2] ✅ 2026-10-31 `/plan-red` Red — acceptance and failing lower-tier tests · 6 red (missing `surmap.demo.history`), then green
  - [x] History store persists a run and returns the cloud at a scrubbed frame, not the final cloud
  - [x] Server persists a streamed run and serves `/runs` + snapshot scrub endpoints
  - [x] Map events carry sampled raw cloud points for the browser 3D view
  - [x] Page carries timeline rewind/forward, runs picker, resizable/fullscreen PTZ point-cloud pane
- [wf 3] ✅ 2026-10-31 `/green` Green — implement until every red test passes · 619 passed, 3 skipped; ruff + mypy strict green
  - [x] `RunHistoryStore` (stdlib sqlite3) in `src/surmap/demo/history.py`
  - [x] Server: persist SSE events per run, `run` event, `/runs` APIs, cloud points in map/final
  - [x] Page: generic test console, history slider + step controls, WebGL point cloud with PTZ, resize + fullscreen
  - [x] Launcher: `--history-db` option
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] Changelog entry written and 1-WIP docs deleted at wrap

## Initial Discovery

See [2026-10-31-generic-test-console-initial-discovery.md](2026-10-31-generic-test-console-initial-discovery.md).

## Prerequisites

Deferred-work cross-check: `src/surmap/docs/todo/` holds only moving-object
records; none touches the demo page, server, or datasets. No restructure
prerequisite.

## State A

Demo page per dataset, ephemeral SSE stream, 2D fixed-size floor plan only;
closing the page loses the run.

## State B

Generic SurMap Test Console: any registered scene runs as a test run;
each run is persisted to SQLite (`demo-history.db`) as it streams;
the timeline slider and step buttons rewind / wind forward through the
persisted frames, showing each frame's image, overlay points,
detections and the point cloud as of that frame; previous runs can be
re-opened from the runs picker. The point-cloud pane is a WebGL 3D view,
drag-resizable, fullscreenable, with PTZ buttons plus mouse orbit /
shift-drag pan / wheel zoom. The 2D floor plan remains as a mini-map.

## Delta

New `history.py`; `server.py` gains run persistence, `/runs` endpoints and
sampled cloud points on map/final events; `page.py` rewritten as the test
console; `scripts/demo.py` gains `--history-db`. Existing SSE kinds,
floor-plan data and playback controls are preserved.

## Verification

- `uv run pytest -q` — 619 passed, 3 skipped (2026-10-31); after the final
  stats-merge edit the demo suites were rerun: 40 passed.
- `uv run ruff check src tests`, `uv run ruff format --check src tests`,
  `uv run mypy` — all green (159 files).
- Rendered page JS extracted and `node --check` clean; server started with
  `scripts/demo.py --no-rtabmap --port 8799`, `/health`, `/` and `/runs`
  all 200. No browser on this machine, so the WebGL pane was not run
  visually — headless `check_page.py` reported no browser available.
- Live-cloud probe (`/tmp/probe_history.py`, FakeLiveBackend through the
  real HTTP stream): snapshot at seq 1 returns that moment's cloud
  `[[1.0, 2.0, 5.0]]` with its colours and `tracking` stats.
- Wrap file-length gate: `page.py` crossed 500 lines with the 3D script,
  so the script moved verbatim to `cloud_script.py` (page 479 lines,
  rendered page byte-checked and JS re-validated). `server.py` was
  already 1,094 lines and grew to 1,223 — flagged in the PR body, not
  split here (no precedent for splitting it; recorded as a finding).
- Later full-suite rerun under load: 617 passed with 2 unrelated
  failures (moving-differencing frame budget, RTAB-Map container e2e);
  on a clean base worktree the first fails identically and the second
  skips — both pre-existing/environmental, not this change.
