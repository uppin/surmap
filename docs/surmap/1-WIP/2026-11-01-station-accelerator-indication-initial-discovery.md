## Combined Conclusions

- Station responses (`StationResponse` → `SamFrameDetections`) carry only
  `frame_id` + detections; a client cannot tell whether SAM ran on GPU or CPU.
- Detectors already know: `Sam3Detector.provider` returns the ONNX provider
  (`CUDAExecutionProvider`/`CPUExecutionProvider`) but exposes no `device`;
  `Sam31TorchDetector` exposes `provider` ("SAM 3.1 (PyTorch)") and `device`
  (`cuda:N`/`cpu`); `InMemorySamDetector` exposes neither.
- `station_server._analyze` builds responses without consulting the detector
  for execution metadata.
- `scripts/verify_cm5.py` verifies only the CM5; there is no station
  verification script. Its patterns (CheckResult/Rate, raw Connect framing,
  EuRoC fixture) are the ones to mirror.
- Deferred-work cross-check (Step 2b): `src/surmap/docs/todo/` and
  `src/surmap/docs/code-issues/` contain no item naming the station server,
  SAM adapters, or the survey proto — nothing blocks this change.

## Exploration 1

### Sequence
1. `read proto/surmap/survey/v1/survey.proto` (SamFrameDetections area) — wire shape.
2. `read src/surmap/survey/station_server.py` — response construction.
3. `read tests/test_survey_station_sam3_e2e.py` — existing CPU fake-model e2e to extend.
4. `read src/surmap/survey/sam.py` — `SamDetector` port and in-memory adapter.
5. `read scripts/verify_cm5.py` — verification script patterns to mirror.
6. `read src/surmap/survey/sam3.py`, `sam3_torch.py` — provider/device surfaces.
7. `read src/surmap/survey/station_main.py`, `scripts/gen_survey_rpc.py`,
   `scripts/deploy-station.sh` — process wiring, proto regeneration, deploy.
8. `grep` docs TODO/code-issues for station/SAM items — none in scope.

### Inspected files
- `proto/surmap/survey/v1/survey.proto` — `SamFrameDetections { frame_id=1, detections=2 }`.
- `src/surmap/survey/station_server.py` — `_analyze()` builds
  `StationResponse(detections=SamFrameDetections(frame_id, detections))`.
- `src/surmap/survey/sam3.py` — `Sam3Detector.provider` → session provider;
  session `device` exists on `Sam3Session` protocol but not on the detector.
- `src/surmap/survey/sam3_torch.py` — `Sam31TorchDetector.provider`/`.device`.
- `tests/test_survey_station_sam3_e2e.py` — fake ONNX model on CPU through a
  real socket server (`running_server`, `_connect_bidi` helpers).

### Findings
- The wire addition is two optional strings on `SamFrameDetections`;
  regeneration is `uv run --with grpcio-tools==1.73.1 python scripts/gen_survey_rpc.py`.
- GPU vs CPU is decidable client-side from `device` (`cuda*` → GPU) and
  corroborated by `provider` (`CUDAExecutionProvider` → GPU).
- The demo fixture (`tests/fixtures/euroc_v101_rtabmap`) and the fake SAM3
  model fixture already cover both verification paths (CPU locally, GPU live).
