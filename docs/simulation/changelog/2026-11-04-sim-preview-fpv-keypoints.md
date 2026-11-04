# 2026-11-04 — The chat's simulation preview: only the camera, overview then FPV with RTAB-Map keypoints

- Page: `?view=preview` (`preview.rs`) shows one view edge to edge — no header, hint, stereo
  panel, HUD or Take off button. Overview (chase + PTZ) while the viewed drone is docked / not
  engaged; FPV (left camera, letterboxed) once airborne. With `?bridge=` the FPV is the held
  frame RTAB-Map answered for, with its keypoints as depth-coloured dots (`HeldFrames`,
  `FpvFrame`, `fleet::stream::parse_odometry`); without, the live eye. `?bridge=` may be
  percent-encoded (the chat's `URLSearchParams` writes `ws%3A%2F%2F…`); `bridge_url` decodes it.
- Wire: the bridge `status` reply gains `odometry: [{frame_id, keypoints: [[u, v, depth]]}]`
  (omitted when empty; goldens unchanged). `DroneSession` fills it from the odometry it polls,
  mapped to raw pixels through the backend's `rectification` (now part of the
  `StreamingBackend` protocol); `rectified_to_raw` moved to `surmap.slam.keypoint_pixels`, the
  demo re-exports it.
- Chat: `SimulationPane` embeds `…&view=preview&fleet=1[&bridge=…]`; `bridgeUrl` from `?bridge=`
  or `VITE_SURMAP_BRIDGE_URL`.
- `scripts/dev.sh --bridge`: prepares the streaming RTAB-Map image first
  (`SURMAP_DEV_RTABMAP_INIT_CMD`), then the agent's bridge on `SURMAP_DEV_BRIDGE_PORT` (8782) and
  the chat's bridge URL. The sim page is now also rebuilt when it is older than the sim's source
  (it kept serving a stale page before), and as trunk's incremental dev build, not `--release`.
- Verification: pytest 2539 passed / 10 skipped, cargo test 391, vitest 161; ruff, mypy,
  eslint (2 existing warnings), tsc clean. V4 in Chrome against the real sidecar: overview
  landed, FPV with keypoints airborne. `Entity despawned` console warnings appear on the full
  page too (existing eye-readback path).
