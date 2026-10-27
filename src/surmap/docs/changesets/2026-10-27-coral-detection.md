# Coral object detection and tracking

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added the Coral Edge TPU detection component behind
`surmap.detection`: `CoralDetector` (EfficientDet-Lite0 INT8 by
default; `ssd-mobilenet-v2` and `ssdlite-mobiledet` profiles in
`MODEL_PROFILES`), a CPU `IouTracker` assigning persistent track
IDs, and `CoralDetectionSource` serializing both. A Meta model was
spiked first and rejected on evidence — no Meta(-family) model runs
compiled on the Edge TPU as a detector — recorded in
`docs/coral-edge-tpu-model-spike.md`.

Wire: detections are a separate stream, never attached to survey
output frames. `Cm5SurveyService.StreamDetections` (proto +
regenerated bindings) emits `FrameDetections{frame_id, t_ns,
detections[label, score, box, track_id]}` per analyzed channel-0
frame; clients join by `frame_id`. The same source also backs
`CoralObjectPointSource`, lifting tracked boxes' stereo points into
survey object batches (designations ≥ 100).

Tooling: `scripts/fetch_coral_model.py` pins all profiles' Edge-TPU
+ CPU-twin artifacts by SHA-256. The CPU twin proves the real network
in CI (no Coral board there); `--coral-edgetpu` selects the compiled
artifact + delegate on hardware. Model choice is exposed at every
surface: `cm5_main --coral-model`, demo `--coral-model`, and
`scripts/deploy-cm5.sh --model <profile> [--coral-cpu]`, which
renders `--detector coral …` into the systemd unit. The demo
overlays tracked boxes from its own detections events, joined by
frame_id.

Verification: tracker/detector/profile unit tests, detections-stream
handler and proto tests, deploy-script tests, and
`tests/test_survey_cm5_coral_e2e.py` — real CM5 server, real model
(CPU twin) on EuRoC frames: a separate frame-keyed detections stream
with persistent tracks plus real object point batches, server closed
afterwards (CI: `coral-e2e` job). All three profiles were also probed
through `CoralDetector` on EuRoC frames (MobileDet hit 10/10).
