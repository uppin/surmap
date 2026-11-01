## Combined Conclusions

- The demo (`scripts/demo.py`, `surmap.demo.server`) runs everything
  in-process today: RTAB-Map via a local `LiveSlamBackend`, Coral via a
  local `DetectionSource`, SAM via a local `VideoSamDetector`/`VideoSamStreamer`.
  It never talks to the deployed CM5 or Station servers.
- The seams are the right shape for wire clients: `LiveSlamBackend`
  (process_frame/poll_updates/map_cloud/trajectory/flush/close),
  `DetectionSource.detect_tracked(frame_id, rgb)`,
  `VideoSamDetector.reset/track/close`. `backend_factory` in tests is
  a zero-arg callable returning the fake backend.
- The survey wire has no capabilities surface and no trajectory message:
  `Cm5Response` is points (designation 1 = scene, >=100 = object) or
  echoed video. Station responses now carry `provider`/`device`
  (previous changeset).
- Decisions (developer, 2026-11-01): full remote pipeline; a server
  capabilities RPC on both services; CM5 panes hidden while the CM5
  host is offline; the Radxa CM5 (10.88.77.14, RTAB-Map native, no
  detector) fills the CM5 role for now. Demo deploys on the Station
  host (10.88.77.10).
- Step 2b cross-check: no TODO/code-issue record names the demo server,
  the survey services, or the proto — nothing blocks.

## Exploration 1

### Sequence
1. `read scripts/demo.py` — launcher options (all local pipelines).
2. `read src/surmap/demo/server.py` (chunks) — `LiveSlamBackend` protocol,
   `_DetectionWorker`, `_SamWorker`, `RunSession`/`DemoPlayer`,
   `make_demo_server` options and page-state wiring.
3. `grep` demo page (`page.py`) for panes — SAM pane gated by
   `server.sam_enabled`; cloud/RTAB pane always rendered.
4. `grep` proto for services — `Cm5SurveyService` (StreamSurvey,
   StreamDetections, StreamMovingAreas, StreamRegionPoints),
   `StationSamService` (StreamAnalysis); no unary RPC anywhere yet.
5. `grep` tests for `backend_factory` — zero-arg factory protocol used
   by demo tests; per-scene calibration lives in `RunSession`.

### Findings
- Remote CM5 map: accumulate designation-1 batches into the cloud;
  trajectory/odometry/keypoints have no wire source (adapter reports
  empty/None); object batches map to designation layers.
- Remote Coral: one short StreamDetections exchange per frame
  (tracker state lives server-side, so track ids persist).
- Remote SAM: one short StreamAnalysis exchange per frame plus
  client-side IoU association for persistent track ids, mirroring
  `Sam3VideoDetector`'s association over the ONNX session.
- Capabilities must be explicit (chosen over probing): a unary
  `GetCapabilities` on both services, filled from what each server was
  actually built with.
