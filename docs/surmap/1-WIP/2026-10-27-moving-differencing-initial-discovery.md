# Initial discovery — differencing + moving areas (n3)

Shared whole-work discovery:
[2026-10-27-moving-snippets-initial-discovery.md](./2026-10-27-moving-snippets-initial-discovery.md).

Node-specific findings:

- Design §4 steps 1–2 specify the static layer (voxel hash,
  log-odds + decay, dwell test), `τ(Z, θ̂)`, cluster-level
  persistence (the peer-review issue-1 fix), mask→polygon areas,
  and velocity/depth-scaled association.
- The wire contract (design §4) adds `StreamMovingAreas` to
  `Cm5SurveyService` in `proto/surmap/survey/v1/survey.proto`;
  handler patterns are `stream_survey` / the detections stream
  in `src/surmap/survey/cm5_server.py`; bindings regenerate via
  `scripts/gen_survey_rpc.py` (pinned `grpcio-tools==1.73.1`).
- `src/surmap/survey/stereo.py` `StereoReconstructor` already
  produces the half-resolution stereo points stage 1 consumes.
- Threshold/config home: alongside `surmap.motion.classify_motion`
  (design OQ4).
