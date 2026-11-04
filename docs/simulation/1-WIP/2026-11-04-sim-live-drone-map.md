# Changeset: The chat's live drone map — the demo's follow view of the map the drone builds

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — two packages (Python agent server, chat), one new HTTP route, reuses the demo's renderer

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + discovery
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests · pytest 13 red (missing API), vitest 7 red
  - [x] Python: `follow_camera`, `render_follow_view`, `FleetPerception.drone_map`, `GET /sim/map/<id>`
  - [x] Chat: `getDroneMap` on the port, `DroneMapPane`, the page shows it once a drone flies
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · pytest 2612 passed, vitest 181 passed
  - [x] `cloud_view.follow_camera` / `render_follow_view` (the demo's Follow framing, default pose)
  - [x] `StreamingBackend.map_cloud`; `DroneSession` keeps its last pose; `FleetPerception.drone_map`
  - [x] `sim_routes.drone_map` behind `GET /sim/map/<id>`, with CORS
  - [x] Chat: port + adapter, `DroneMapPane`, polling in `ChatPage`
- [wf 4] ⏳ `/pr-wrap` Wrap — validate, clean up, verification, docs · V1 green; V4 in the browser not yet run
  - [ ] Verification executed — result recorded
  - [x] `docs/simulation/bevy-simulation.md` — the live drone map
  - [x] `docs/simulation/changelog/` entry
  - [x] Python gates (ruff format/check, mypy, pytest), chat gates (lint, typecheck, test)

## Initial Discovery

[2026-11-04-sim-live-drone-map-initial-discovery.md](2026-11-04-sim-live-drone-map-initial-discovery.md)

## State A

The chat's simulation pane shows the camera preview only. RTAB-Map's map of each drone exists on
the server (`DroneSession.backend.map_cloud()`) but nothing shows it outside the demo page.

## State B

- **Route.** `GET /sim/map/<scenario>` (`sim_routes.drone_map`): 404 for an unknown scenario; 204
  while no page streams the scenario, before any drone's frames, or while the drone streamed now
  is `docked` (fleet telemetry); otherwise 200 JSON
  `{"drone_id", "phase", "points", "png"}` — `png` is the drone's map drawn with the demo 3D
  pane's Follow view (`cloud_view.render_follow_view`: behind and above the drone along its
  heading, the drone at 3/4 height, 24 m across, a yellow arrow at it), base64. CORS like
  `/datasets`.
- **Perception.** `StreamingBackend` gains `map_cloud()`. `DroneSession` keeps its last odometry
  pose (`map_pose`, else `pose`); `FleetPerception.drone_map()` is the processing drone's
  `DroneMap(drone_id, cloud, pose)`, `None` before any pair.
- **Chat.** `ChatPort.getDroneMap(scenarioId)` → `DroneMapView | null`. With a simulation open,
  `ChatPage` polls it every second; the first map shows `DroneMapPane` ("Live map", the drone's
  id and point count, the image) under the simulation pane, and it stays with its last image after
  the drone lands.

## Delta

Changed: `demo/cloud_view.py`, `simulation/bevy_bridge.py` (protocol), `simulation/fleet/
perception.py`, `agent/server/sim_routes.py`, `agent/server/routes.py`, chat `ports.ts`,
`adapters/connect-chat.ts`, `ChatPage.tsx`. New: `components/DroneMapPane.tsx`.

## Verification

V1 — pytest (renderer, perception, the route over the real server with a fake page and fake
maps), vitest (pane, page polling, adapter). V4 — manual: `scripts/dev.sh --bridge`, launch a
drone, see the live map pane appear and grow.
