# Initial discovery — the agent chooses the on-board detector model

**Date**: 2026-11-04
**Changeset**: [2026-11-04-agent-onboard-model-choice.md](2026-11-04-agent-onboard-model-choice.md)

## Request

> the agent should be able to also choose onboard image recognition model (or choose not to have
> it) to process the input

## What exists

- **On-board detection** is the Coral Edge TPU detector + IoU tracker (`surmap.detection`). Its
  selectable networks are the `MODEL_PROFILES` registry (`surmap/detection/profiles.py`):
  `efficientdet-lite0` (default), `ssd-mobilenet-v2`, `ssdlite-mobiledet`. Each profile is two
  pinned files in a prepared model dir (`scripts/fetch_coral_model.py`).
- **The demo player** takes one `detection_source` (`DemoPlayer(..., detection_source=...)`); a
  `_DetectionWorker` runs it off the frame loop and emits `detections` events. `make_demo_server`
  builds it once, host-wide, from `coral_model_dir` + `coral_model`
  (`coral_detection_source`, CPU twin).
- **The agent** runs scenes through `DemoWorkspace._start`, which already overrides the host's
  player options per run (`fps`, `max_frames`, and `run_rtabmap`'s SAM-off overrides). The run's
  SAM prompt is recorded in the run title (` · SAM: <prompt>`) and read back by `_prompt_of`.
- **The agent CLI** (`python -m surmap.agent`) has no Coral flags; `build_demo_workspace` builds
  the host without a detection source, so agent runs never run on-board detection today.
- `CoralDetector` raises `DetectorUnavailable` when the model file is missing; the TFLite runtime
  loads lazily on first detect.

## Gaps

1. No tool says which on-board models the station has.
2. `run_demo` / `run_rtabmap` cannot pick a model or turn detection off.
3. A run does not record which on-board model processed it.
4. The agent process cannot be pointed at a Coral model dir.
