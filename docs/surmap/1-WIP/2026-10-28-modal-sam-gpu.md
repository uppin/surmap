# Changeset: Modal GPU for the ONNX SAM path

**Date**: 2026-10-28
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package, HTTP adapter seam, fake-endpoint tests, no live Modal

## Workflow

- [wf 1] ✅ 2026-10-28 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
- [wf 2] ✅ 2026-10-28 `/plan-red` Red — acceptance and failing lower-tier tests, committed · collection error, `surmap.survey.modal_sam` missing
- [wf 3] ✅ 2026-10-28 `/green` Green — implement until every red test passes · `tests/test_modal_sam.py` 13 passed
  - [x] `ModalSamSession` calls `MODAL_SAM_URL` and fails before a request when it is unset
  - [x] Fake endpoint masks become a `SamDetection` with a non-empty polygon via `Sam3Detector`
  - [x] `before_call("modal")` runs before the request and can block it
  - [x] `on_usage("modal", model, 0, 0, None)` and `on_gpu_seconds` record the remote elapsed time
  - [x] Remote `segment_payload` returns its own inference seconds
  - [x] App function kwargs: configurable GPU default `T4`, `timeout`, `scaledown_window` 60, `max_containers=1`, no `min_containers`
  - [x] `station_main` selects the Modal session with `--detector sam3-modal` or `--sam3-device modal`
  - [x] Importing the modules does not require the `modal` package
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `HACKATHON.md` — Modal row reworded; deploy, stop, and spend documented
  - [ ] `docs/surmap/changelog/2026-10-28-modal-sam-gpu.md` written
  - [ ] README.md not edited (PR #28 review)
  - [ ] `docs/architecture.md` not edited (open on PR #18)
  - [ ] Planning documents removed from `docs/surmap/1-WIP/`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-28-modal-sam-gpu-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: station SAM session and `station_main`. `README.md` is intentionally unchanged.
  - [HACKATHON.md](../../../HACKATHON.md) — Modal credit row and the deploy/stop/spend runbook (file is added here because it is not on `main`; prose matches PR #28 except the Modal row)
  - [changelog](../changelog/2026-10-28-modal-sam-gpu.md) — history entry at wrap

## Related Feature Documentation

- [PRD](./PRD-2026-10-28-modal-sam-gpu.md)
- Task: https://github.com/uppin/surmap/pull/28#issuecomment-6479197917

## Summary

Add a Modal GPU session for the existing SAM 3.1 ONNX contract, selected from `station_main`, tested with a fake endpoint, and capped so a forgotten deploy cannot keep a warm GPU pool.

## Background

The local ONNX session already segments on CPU or CUDA. Hackathon Modal credit is for running that same exported model on a Modal GPU. The checkpoint stays on a Volume. CI has no Modal account. A parallel branch may add token accounting in `src/surmap/usage.py`; this session accepts the callbacks and does not import that module.

## Scope

- Client `ModalSamSession` and remote app module next to it
- `station_main` switch
- Fake-endpoint and fake-Modal tests
- Module docstring and `HACKATHON.md` runbook (`modal deploy`, `modal app stop`, dashboard spend)
- No keys, no `modal` dependency in `pyproject.toml`, no README edit

## Technical Changes

### State A (Current)

- `Sam3Detector` takes a `Sam3Session`. The only session is `OnnxSam3Session`.
- `station_main --detector sam3` requires `--sam3-model` and a device of `auto`, `cpu`, or `cuda`.
- Nothing in `src/` calls Modal. `HACKATHON.md` is not on `main`.

### State B (Target)

- `ModalSamSession` is a `Sam3Session`. It POSTs the NCHW float32 tensor to `MODAL_SAM_URL` and returns `masks` and `scores`.
- A missing URL raises `Sam3Unavailable` in the constructor, before `before_call` and before any POST.
- Successful responses call `on_usage("modal", "<app>/<gpu>", 0, 0, None)` and `on_gpu_seconds` with the remote `inference_seconds`.
- `surmap.survey.modal_sam_app` builds a Modal App named `surmap-sam` only when `modal` imports. The function uses GPU `T4` unless `SURMAP_MODAL_GPU` is set, `timeout` 300 seconds, `scaledown_window` 60 seconds, `max_containers=1`, and does not set `min_containers`. The ONNX file is read from Volume `surmap-sam3` at `/models/sam3.1.onnx`.
- `--detector sam3-modal` and `--detector sam3 --sam3-device modal` construct that session. A local model path is not required.
- `HACKATHON.md` tells the owner how to deploy, how to stop, and where spend appears.

### Delta (What's Changing)

#### surmap

- **API**: `ModalSamSession`, `modal_sam_detector`, `segment_payload`, `build_app`, `load_app`. `station_main` detector and device choices grow.
- **Implementation**: stdlib HTTP client. Modal SDK stays behind `importlib`.
- **Dependencies**: none added to `pyproject.toml`.

## Verification

### V1 — behaviour

Commands and the pass/fail line are recorded when the Wrap row runs them.

- `uv run pytest -q tests/test_modal_sam.py tests/test_sam3.py`
- `uv run ruff check src tests`
- `uv run ruff format --check src tests`
- `uv run mypy`
- `uv run pytest -q`
