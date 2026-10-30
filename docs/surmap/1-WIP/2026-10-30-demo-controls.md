# Changeset: Demo scene selection and playback control

**Date**: 2026-10-30
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — server catalog + control endpoint, player pause/cancel, stream takeover, page controls

## Workflow

- [wf 1] ✅ 2026-10-30 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
  - [x] Record initial discovery (server surface, player loop)
  - [x] Create changeset
- [wf 2] ✅ 2026-10-30 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 10 red; `_prepared_tiny` typed, 9 `type: ignore[arg-type]` removed from test_demo.py
  - [x] Datasets: an already-prepared scene is found in the cache without downloading
  - [x] Datasets: preparing reports progress — downloading bytes, verifying, extracting files, ready
  - [x] Server: `/datasets` lists every scene with its state (cached / preparing with progress / error) and the current one
  - [x] Server: `POST /prepare?dataset=` prepares a scene in the background; progress shows on `/datasets`; a cached scene is never fetched again
  - [x] Server: `/?dataset=` serves any registered scene's page; `/stream?dataset=` streams it once prepared; unknown 404, not prepared 409
  - [x] Server: a new stream takes over from the running one, which ends and tears down
  - [x] Player: paused playback emits no frames and feeds no pairs until resumed
  - [x] Player: a cancelled player stops and closes its backend
  - [x] Server: `POST /control` pauses and resumes the running stream; bad action 400, no stream 409
  - [x] Run the new tests (verify they fail for missing implementation)
- [wf 3] ⏳ `/green` Green — implement until every red test passes · 565 passed, 2 skipped; pause/resume verified over HTTP on the live KITTI stream, browser look pending
  - [x] `cached_dataset()`, progress callback in `ensure_dataset`; launcher downloads nothing at start
  - [x] `PlaybackControls` in the player loop (pause keeps releasing held frames)
  - [x] Server catalog, per-scene page/stream, takeover, `/control`
  - [x] Page: scene picker (every scene), download/extract progress bar, Pause/Resume, Restart
  - [ ] Real check in the browser on EuRoC and KITTI
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] `README.md` §Demo — scene picker and playback controls
  - [ ] Changelog entry `docs/surmap/changelog/2026-10-30-demo-controls.md`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-30-demo-controls-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Stack Context

Stacked on `feat/kitti-demo` (changeset `2026-10-30-kitti-demo.md`), itself on
`feat/live-map-display`: needs the second scene and per-scene page tuning.

## Affected Packages

- **surmap**: `demo/datasets.py`, `demo/server.py`, `demo/page.py`
- **scripts**: `scripts/demo.py`

## Summary

The demo page gains a scene picker and Pause/Resume/Restart. One server
serves every scene already in the cache; the newest viewer takes the
stream over instead of being refused.

## Technical Changes

### State A (Current)

- One scene per server process; switching means restarting the launcher.
- A second stream request gets 409; no way to pause.

### State B (Target)

- `cached_dataset(spec, cache_dir) -> PreparedDataset | None` reads a
  prepared scene's manifest, never downloads.
  `ensure_dataset(…, progress=…)` reports `PrepareProgress(phase,
  done, total)` — `downloading` (bytes), `verifying`, `extracting`
  (files), `ready` — for the main and calibration zips.
- `make_demo_server(prepared=None, *, catalog=DATASETS, cache_dir, default_dataset, fetch, …)`
  serves every catalog scene. The launcher downloads nothing at start.
- `GET /datasets` → `{"current", "datasets": [{"id", "title",
  "description", "state": "missing" | "preparing" | "ready" | "error",
  "progress": {"phase", "done", "total"}, "error"}]}`.
  `POST /prepare?dataset=<id>` starts one background preparation per
  scene (idempotent) into the cache; a cached scene is not fetched again.
- `GET /?dataset=<id>` renders any catalog scene's page from its spec
  (default: `default_dataset`); `GET /stream?dataset=<id>` streams it
  once prepared; unknown id 404, not prepared 409.
- `PlaybackControls` (`pause`, `resume`, `cancel`, `paused`,
  `cancelled`). `DemoPlayer(controls=…)`: while paused it feeds no pairs
  and emits no frames, but keeps polling SLAM and releasing held frames;
  when cancelled it stops and its `finally` closes worker and backend.
- A new `/stream` cancels the running player and waits (≤ 10 s) for the
  stream lock, instead of 409. `POST /control` with `{"action": "pause" |
  "resume"}` acts on the running player → `{"state": "paused" |
  "playing"}`; unknown action 400, no running stream 409.
- Page: scene `<select>` over every scene navigates to `/?dataset=<id>`.
  A scene not yet prepared starts `POST /prepare` and shows a progress
  bar (phase, MB / files) polled from `/datasets`, then starts the
  stream. Pause/Resume posts `/control`; Restart reloads the page.

## Verification

**Method:** V1 fail→pass and a manual browser check.
**Command:** `uv run pytest -q tests/test_demo_controls.py`; launcher with both scenes cached.
**Before:** new tests fail; the page has no controls.
**After:** tests green; full gates green; browser check recorded at wrap.

## Decisions & Trade-offs

- **Download on first pick, from the page (user decision).** Nothing is
  pre-downloaded; picking a scene fetches it once into the cache with a
  visible progress bar, and later picks are cache hits. Preparation runs
  in the background and does not stop a running stream.
- **No seek or speed.** The live map cannot rewind; above-native speed
  only drops more pairs under emulation. Restart replays from the start.
- **Newest viewer wins.** Replaces the 409 that surfaced as "Stream
  unavailable"; one SLAM sidecar at a time is kept.
