# Initial discovery — moving-object whole work (shared by n2–n6)

Combined conclusions (from the design research on PR #17, n1):

- The moving-object design (`docs/moving-object-detection-design.md`)
  is the PRD for the feature nodes. Its §6.1/§6.2 evaluation
  programme needs real-video snippets: monocular traffic (VisDrone
  MOT / Commons Byrne fallback), forest fire (Boreal / Commons
  Wennington fallback), drone swarm (Purdue UAV_Dataset), and one
  stereo+calibration snippet (KITTI tracking) for the RTAB chain.
- Candidate evaluation is recorded in design §6.1/§6.2 with
  licenses, URL stability checks (HEAD requests, 2026-10-27), and
  inspected frames. Purdue annotation ranking picked `Clip_50` /
  `Clip_28`; KITTI label ranking picked sequences 0020/0009/0001.
- The RTAB sidecar (`src/surmap/slam/sidecar.py`,
  `SidecarRtabmapBackend`) consumes EuRoC layout
  (`mav0/cam{0,1}` PNGs + `sensor.yaml` + IMU csv) and has a
  stationary-IMU fallback; KITTI converts into that layout.
- Existing seams reused, not reinvented: `surmap.survey.stereo`
  (`StereoReconstructor`), `surmap.detection` (Coral detector +
  `IouTracker`), `surmap.motion.classify_motion`,
  `surmap.survey.cm5_server.stream_survey` /
  `stream_detections` handler patterns, pinned proto regeneration
  via `scripts/gen_survey_rpc.py` (`grpcio-tools==1.73.1`).
- Host for calibration spikes: RTX 5060 Ti 16 GB (CUDA 13.2),
  COLMAP 4.2.1 with CUDA at `~/.local/bin/colmap` (verified).
- No `<package-dir>/docs/code-issues/` or `docs/todo/` records
  exist for `src/surmap` — nobody has analyzed it; that is not
  the same as clean. No deferred-work prerequisites found for
  this stack.
