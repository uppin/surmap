# Changeset: Local Ollama (Gemma) live mission

**Date**: 2026-11-02
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — more than one package seam: new labelling + segmentation adapters behind existing ports, mission wiring, live local run

## Workflow

- [wf 1] ✅ 2026-11-02 `/plan-red` Plan — changeset, no PRD (operator-selected local alternative, no new user surface) · this file; local model `gemma4:e4b-mlx` confirmed in `ollama list`, vision smoke OK (~15 s/frame)
- [wf 2] ✅ 2026-11-02 `/plan-red` Red — failing tests for the Ollama adapters and mission selection · red on missing modules, then on missing model option
  - [x] Label/scene clients post to `/api/chat` and parse replies; empty reply fails by name
  - [x] Box detector scales 0–1000 boxes to frame pixels with rectangle masks
  - [x] `SURMAP_LIVE_OLLAMA=1` selects ollama for SAM, labels, and scene note with no API key
- [wf 3] ✅ 2026-11-02 `/green` Green — implement until every red test passes · live run: `basis: "live"`, 0 of 7 found (Gemma saw no person in the ground-facing hover frames), local scene note recorded, `meta_calls: []`
  - [x] `surmap.labelling.ollama` clients behind the existing label/scene ports, recording fake transport in tests
  - [x] `surmap.survey.ollama_box` detector behind the segmentation seam (any Ollama vision model via `--ollama-model` / `SURMAP_OLLAMA_MODEL`)
  - [x] Mission wiring; run `--live` on `~/sitl-runs/disaster-mac` and record the score
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/mission-demo.md` — Ollama path documented
  - [ ] Four gates green: ruff check, ruff format, mypy, pytest

## Initial Discovery

`MODEL_API_KEY` gates only hosted Meta calls in `build_live_services` (`src/surmap/mission/demo.py`): Meta SAM masks, Muse Spark labels, Muse Spark scene note. Everything else in the live chain (RTAB-Map Docker, geometry, scoring) is local. `_live_segmenter` has only Meta/Modal branches, so no key means no masks and the mission refuses to start. The user selected a fully local alternative: Ollama serving the locally stored `gemma4:e4b-mlx`, replacing all three roles. Gemma cannot emit mask polygons, so its detections are bounding boxes carried as rectangle mask polygons — the same `SamDetection` contract, with the coarser mask stated in the adapter docstring.

## Verification

| Check | Before | After (planned) |
|---|---|---|
| `--live` without any API key | exit 2, `MODEL_API_KEY is not set` | with `SURMAP_LIVE_OLLAMA=1`, runs and writes `impact.json` |
| Ollama calls in report | n/a | `model_ids` name `ollama:gemma4:e4b-mlx`; no Meta call is made |
| Existing live selections | meta/baseten/modal tests green | unchanged, still green |

Verification executed 2026-11-02: the after-run above ran fully locally
(`SURMAP_LIVE_OLLAMA=1 ... --ollama-model gemma4:e4b-mlx`) and wrote
`mission-demo-out-live/impact.json` with `basis: "live"`,
`map_backend: "live-rtabmap"`, a Gemma scene note, and `meta_calls: []`;
score 0 of 7 because the hover capture's frames face bare ground (the
same frames returned `[]` in the pre-implementation smoke test). Full
gates after the final edit: ruff check clean, format clean, mypy strict
clean (237 files), pytest 997 passed / 6 skipped.
