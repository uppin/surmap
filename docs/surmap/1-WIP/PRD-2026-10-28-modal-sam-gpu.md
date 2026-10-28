# Modal GPU for the ONNX SAM path - PRD

**Date**: 2026-10-28
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Station SAM 3.1 (`src/surmap/survey/sam3.py`, `station_main`) — a second session that runs the same ONNX contract on a Modal GPU. No separate feature doc on `main`. `README.md` is not edited. `docs/architecture.md` stays on the PX4 branch.

## Summary

The station can send the existing SAM 3.1 ONNX tensor to a Modal GPU and turn the returned masks into the same `SamDetection` polygons the local CPU/CUDA path already produces. CI never contacts Modal.

## Background

Hackathon follow-up task 4 (PR #28 comment 6479197917). Modal credit is for inference on the exported ONNX model, not a second segmenter. The checkpoint is license-gated and stays off git. The owner authenticates Modal locally (`modal token new`, workspace `ginas-bb`). A parallel change may add `src/surmap/usage.py`; it is not on `main`.

## Proposed Changes

### What's Changing

- `ModalSamSession` implements `Sam3Session` by POSTing the image tensor to `MODAL_SAM_URL`.
- An unset or blank URL fails before any request.
- The remote app runs ONNX Runtime on a GPU. The checkpoint comes from a Modal Volume, never from git.
- GPU type is configurable and defaults to `T4`. The function sets `timeout`, `scaledown_window` of 60 seconds, and `max_containers=1`. It does not set `min_containers`.
- The remote response includes the function's own elapsed inference time.
- Optional `before_call("modal")` runs before each request and may raise to block it.
- Optional `on_usage("modal", "<app>/<gpu>", 0, 0, None)` and `on_gpu_seconds(inference_seconds)` run after a successful response.
- `station_main` accepts `--detector sam3-modal` or `--detector sam3 --sam3-device modal`.
- `HACKATHON.md` states the deploy command, the stop command, and where to see spend.

### What's Staying the Same

- `Sam3Detector` preprocessing and polygon post-processing.
- `OnnxSam3Session` for local CPU and CUDA.
- Existing `tests/test_sam3.py`.
- `README.md` and `docs/architecture.md`.
- No Modal account, token, or package in CI.

## Impact Analysis

### Technical Impact

- New modules `surmap.survey.modal_sam` and `surmap.survey.modal_sam_app`.
- `modal` is imported only inside the app module, via `importlib`, when the package is installed. Tests pass a fake endpoint and a fake Modal object.
- Deploy is a manual owner step in WSL. This PR does not deploy.

### User Impact

- Station operators who set `MODAL_SAM_URL` can select the Modal detector.
- Without that URL the process fails at startup with a typed error, before a request.
- Cost stays bounded unless the owner changes the GPU, raises the timeout, or stops forgetting `modal app stop`.

## Implementation Plan

1. Failing tests for the fake endpoint, the URL guard, the hooks, the remote elapsed time, and the cost limits.
2. Client, remote app, and `station_main` switch.
3. `HACKATHON.md` runbook. No README edit.

## Acceptance Criteria

- [ ] A fake endpoint returning masks `[1, N, H, W]` and scores `[1, N]` produces a `SamDetection` with a non-empty polygon
- [ ] Unset URL fails before any request
- [ ] `before_call("modal")` can block the request
- [ ] Usage hooks record `modal`, zero token counts, and the remote GPU seconds
- [ ] Remote function returns its own elapsed inference time
- [ ] Published function defaults to a small GPU, a timeout, 60s scale-down, one container, and no keep-warm
- [ ] CI collects and passes with no Modal package
- [ ] Module docstring and `HACKATHON.md` document `modal deploy`, `modal app stop`, and the spend page
- [ ] ruff, mypy strict, and pytest pass

## References

### Related Documentation

- PR #28 comment: https://github.com/uppin/surmap/pull/28#issuecomment-6479197917
- Modal web endpoints: https://modal.com/docs/guide/webhooks
- Modal scale: https://modal.com/docs/guide/scale
