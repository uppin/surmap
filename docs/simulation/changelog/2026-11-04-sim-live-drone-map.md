# 2026-11-04 — The chat's live drone map: the demo's Follow view of what the drone builds

- Chat: a **Live map** pane appears under the simulation pane once the simulation's drone flies —
  its RTAB-Map cloud, drawn like the demo page's 3D pane with Follow on (behind and above the
  drone, its yellow arrow at 3/4 height). It polls every second and keeps the last image after
  landing (`DroneMapPane`, `ChatPort.getDroneMap`).
- Server: `GET /sim/map/<scenario>` — 200 `{drone_id, phase, points, png}` for the drone streamed
  now while telemetry has it off the ground, 204 otherwise, 404 for an unknown scenario; CORS like
  `/datasets`.
- Renderer: `cloud_view.follow_camera` (a pose's floor camera) and `render_follow_view` (the
  Follow framing at the default pose, no session).
- Perception: `StreamingBackend.map_cloud()` joins the protocol; `DroneSession` keeps its last
  odometry pose; `FleetPerception.drone_map()`.
- Verification: pytest 2612 passed / 38 skipped, vitest 181; ruff, mypy, eslint (2 existing
  warnings), tsc clean. Browser V4 against the real sidecar skipped at the developer's decision (not run).
