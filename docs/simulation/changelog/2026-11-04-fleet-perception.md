# 2026-11-04 — The active drone's stream is mapped and segmented, one RTAB-Map per drone (#drone-fleet 5/5, PR #121)

- Wire: optional `drone_id` on `pair` (Rust `PairHeader.drone_id`, `encode_pair`; Python
  `BevyPair.drone_id`), optional `scenario` on `hello`, `drone_id` on `status`. The old
  goldens (`hello.bin`, `pair.bin`) stay byte-identical; `pair-drone.bin` pins the labelled form.
- Station: `surmap.simulation.fleet.perception` — `FleetPerception` routes each pair to its
  drone's `DroneSession` (RTAB-Map backend, `SamSegmentationSink` on its left frames, optional
  recorder, counts), created on first frames, kept alive idle, resumed on switch-back, finished
  on page close in drone-id order. `MAX_DRONE_SESSIONS = 4` per connection; a fifth drone is
  refused with a status naming the limit. `PerceptionRegistry` finds a scenario's page.
- Agent: `python -m surmap.agent --bevy-bridge-port` starts the bridge with the streaming
  RTAB-Map factory and the configured SAM detector; `FleetTools.DroneMapStatus`
  (SYNC · 10 s · FAIL) reports each drone's frames, posed, lost, keyframes, segmented frames,
  detections, `processing` and `last_t_ns` (`UNAVAILABLE` with no streaming page).
- Page: `?bridge=ws://…` streams the active drone's eyes at the camera rate (`StreamPacer`,
  drop when the link is backed up), labelled with the active drone id; status replies drive
  the `MAP <drone> · <n> frames · <k> keyframes · tracking` line under the feed panel.
- Resolved `src/surmap/docs/todo/2026-11-03-bevy-live-websocket-stream.md` (the wasm client,
  the status overlay and the agent-served bridge are delivered; its `serve_bevy_sim.py` is
  replaced by `--bevy-bridge-port` + `--sim-dist` on one server). The V4 Chrome run joins
  `src/surmap/docs/todo/2026-11-04-fleet-browser-verification.md` (deferred post-merge by the
  developer, 2026-11-04, as for n3).
- Verification: V1 — 90 passed (`test_fleet_perception.py`, `test_fleet_perception_e2e.py`,
  `test_bevy_wire.py`, `test_agent_fleet_tools.py`) plus the real-sidecar e2e (1 passed); V3
  wasm check passes; V4 deferred (above). Full gates: ruff check/format clean (593 files),
  mypy clean (534 files), pytest 2399 passed / 38 skipped, cargo test 360 passed.
