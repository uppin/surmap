# Changeset: Station responses and verification indicate GPU vs CPU execution

**Date**: 2026-11-01
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — proto/contract change, server + two adapters, new verification script, live GPU proof

## Workflow

- [wf 1] ✅ 2026-11-01 `/plan-red` Plan — changeset, initial discovery · this file + companion
- [wf 2] ✅ 2026-11-01 `/plan-red` Red — acceptance and failing lower-tier tests · station e2e fails on missing provider/device; verify_station suite fails on missing script
  - [x] Station e2e asserts provider/device on every frame (CPU fake model)
  - [x] verify_station unit tests: ordering, detections, missing provider/device, GPU/CPU indicator
  - [x] verify_station replay test against a real local server (CPU indicator)
- [wf 3] ✅ 2026-11-01 `/green` Green — implement until every red test passes · 759 passed, mypy strict clean; live verify: DEVICE GPU (SAM 3.1 PyTorch, cuda:0), 3.9 fps
  - [x] Proto: `provider`/`device` on `SamFrameDetections`, regenerated bindings
  - [x] Station server populates both from the detector; adapters expose `device`
  - [x] `scripts/verify_station.py`: demo stream in, checks + DEVICE indicator + rate out
  - [x] Redeploy station at 10.88.77.10; live verify shows GPU
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [x] Verification executed — result recorded
  - [x] `docs/deployment.md` — station verification + indicator documented

## Initial Discovery

[2026-11-01-station-accelerator-indication-initial-discovery.md](2026-11-01-station-accelerator-indication-initial-discovery.md)

## Prerequisites

Step 2b cross-check: no TODO or code-issue record in `src/surmap/docs/`
names the station server, SAM adapters, or the survey proto. Nothing blocks.

| Record | Verdict |
|---|---|
| `src/surmap/docs/todo/*` (moving-* items) | — unrelated |
| `src/surmap/docs/code-issues/oversized-file-demo-*` | — unrelated |

## State A → State B

**State A.** `SamFrameDetections` carries `frame_id` and detections only.
A client (or an operator) cannot tell whether the station ran SAM on the
GPU or silently fell back to CPU. The only verification script,
`scripts/verify_cm5.py`, covers the CM5; the station has none.

**State B.** Every station analysis response names the execution that
produced it: `provider` (e.g. `CUDAExecutionProvider`, `SAM 3.1 (PyTorch)`,
`InMemorySamDetector`) and `device` (`cuda:N` or `cpu`) on
`SamFrameDetections`. A new `scripts/verify_station.py` feeds the recorded
EuRoC demo stream to a station server, verifies health/responses, and
prints a `DEVICE` indicator (GPU or CPU, from the response fields) plus
the analysis frame rate; `--expect-device gpu|cpu` turns a mismatch into
a failed check.

**Delta.** Proto fields (additive, wire-compatible), server population,
`device` on `Sam3Detector`/`InMemorySamDetector`, new verification script
and its tests, deployment docs.

## Verification

- `uv run pytest -q` (station e2e, proto, verify_station suites included)
- `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy`
- Live: `uv run python scripts/verify_station.py 10.88.77.10:8081 --expect-device gpu`
  against the deployed SAM 3.1 (PyTorch) station.
