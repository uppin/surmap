# Initial discovery — sim preview: overview, then FPV with RTAB-Map keypoints

Changeset: [2026-11-04-sim-preview-fpv-keypoints.md](2026-11-04-sim-preview-fpv-keypoints.md)

## Combined Conclusions

- The chat's `SimulationPane` (`web/agent-chat/src/components/SimulationPane.tsx`) embeds the
  full Bevy page at the scenario URL (`/sim/?scenario=<id>`, `scenario_url` in
  `src/surmap/agent/tools/simulation_core.py`). The page draws everything itself: HTML header and
  hint (`examples/bevy-sitl-poc/index.html`), the chase view, the LEFT/RIGHT stereo panel with the
  calibration readout, the HUD status text and the Take off button (`src/ui.rs`). Squeezed into
  the pane's `h-96` iframe this becomes the cluttered preview in the screenshot.
- The page streams the active drone's stereo pair to the agent's bridge only with
  `?bridge=ws://…` (`src/fleet/bridge_wasm.rs`), and the agent serves that bridge only with
  `--bevy-bridge-port` (`src/surmap/agent/__main__.py`). `scripts/dev.sh` never passes it.
- The bridge (`FleetPerception` in `src/surmap/simulation/fleet/perception.py`, one
  `DroneSession` per drone) answers every pair with a `status` text (`encode_status` in
  `src/surmap/simulation/bevy_wire.py`): counts only. The `OdomUpdate`s it polls from the
  streaming RTAB-Map backend already carry RTAB-Map's odometry inlier keypoints in rectified
  left-camera pixels (`surmap.slam.stream_protocol.Keypoint`) and their `frame_id` (the page's
  `PairHeader.frame_id`). Odometry is asynchronous: frame N's update usually arrives in the
  reply to a later pair.
- The demo page already does this overlay (changelog `docs/surmap/changelog/2026-10-30-live-map-display.md`):
  it holds a frame until its odometry arrives and draws that frame's keypoints mapped rectified →
  raw (`rectified_to_raw` / `keypoint_overlay` in `src/surmap/demo/server.py`), coloured by
  depth. The streaming backend exposes `rectification` (`src/surmap/slam/streaming.py`).
- "Flying": fleet drones have an autopilot `Phase` (`Docked` = on the pad,
  `src/fleet/autopilot.rs`); the legacy keyboard drone has `Flight.engaged` (`src/main.rs`).
  The viewed drone is `viewed_body(ActiveDrone, fleet, legacy)`.
- The PTZ overview is the chase camera orbiting the viewed drone (`src/view_orbit.rs`).
- Gates: Python (`ruff`, `mypy --strict`, `pytest`), the chat (`yarn lint|typecheck|test`), the
  Bevy crate (`cargo test`; CI builds the WASM bundle in `.github/workflows/bevy-wasm-build.yml`).

## Exploration 1

Read: `SimulationPane.tsx` + test, `App.tsx` (`?server=` / `defaultServerUrl`), `index.html`,
`src/main.rs`, `src/ui.rs`, `src/fleet/{stream,bridge_wasm}.rs`, `src/fleet.rs`
(`ActiveDrone`, `Fleet`, `viewed_body`, `fleet_status`), `src/fleet/autopilot.rs` (`Phase`),
`src/view_orbit.rs`, `bevy_bridge.py`, `bevy_wire.py` (`BridgeStatus`, `encode_status`),
`fleet/perception.py`, `slam/stream_protocol.py` (`Keypoint`, `OdomUpdate`, `Rectification`),
`demo/server.py` (`rectified_to_raw`, `keypoint_overlay`, `depth_colour`), `agent/server/app.py`
(`start_bevy_bridge`), `scripts/dev.sh`.
