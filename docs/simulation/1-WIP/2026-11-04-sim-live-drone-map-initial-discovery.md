# Initial discovery — the chat's live drone map

## Combined Conclusions

- The demo page's 3D pane is server-rendered: `surmap.demo.cloud_view` (`CloudViewer`,
  `_follow_framing`, `_render`) draws every map point to a PNG; Follow (on by default) frames
  the scene behind and above the shown frame's camera (`FollowCamera` = x, z, unit dx, dz on the
  floor), the camera at 3/4 of the image height, `FOLLOW_SPAN_M` (24 m) across at zoom 1, with a
  yellow arrow at the camera. The demo derives the camera with `demo.server.floor_camera`
  (optical axis projected on x-z).
- The fleet's maps live in `surmap.simulation.fleet.perception`: one `FleetPerception` per page
  connection to the stereo bridge, a `DroneSession` per drone, each with a streaming RTAB-Map
  backend. `StreamingRtabmapBackend.map_cloud()` returns the placed `MapCloud`; odometry poses
  arrive as `OdomUpdate.pose` / `map_pose` in `DroneSession._process`. `PerceptionRegistry`
  finds a scenario's page; `FleetPerception.processing()` names the drone streamed now.
- Flight phase is known server-side: `FleetRegistry.controller(id).drones()` holds the last
  telemetry (`DroneTelemetry.phase`, `"docked"` on the ground).
- The page streams pairs whether the drone is docked or not (`fleet/bridge_wasm.rs`
  `stream_bridge`), so "flying" must come from telemetry, not from frames arriving.
- `/sim/…` GETs are answered by `sim_routes.serve_simulation` through `routes.serve`, without
  CORS headers; the chat under Vite is another origin, so a chat-fetched route needs `_cors`
  (as `/datasets` does).
- Chat: every network call goes through `ChatPort` (`ports.ts`, `adapters/connect-chat.ts`;
  plain fetch + bearer token for `/sim/import`). `ChatPage` polls the map scene and station with
  `setInterval`. `SimulationPane` embeds the preview iframe; nothing shows the RTAB-Map map.

## Exploration 1

Parent-driven grep/read: `src/surmap/demo/cloud_view.py`, `cloud_script.py`, `server.py`
(`floor_camera`, `render_view` call sites), `src/surmap/slam/streaming.py` (`map_cloud`,
`pose_rotation`), `src/surmap/simulation/fleet/{perception,controller,registry,link}.py`,
`src/surmap/agent/server/{sim_routes,routes,fleet_routes}.py`, `tests/fleet_perception_fakes.py`,
`tests/fleet_tool_fakes.py`, `tests/test_agent_fleet_tools.py`, `web/agent-chat/src/{ports.ts,
ChatPage.tsx,App.test.tsx,components/SimulationPane.tsx,adapters/connect-chat.ts}`,
`examples/bevy-sitl-poc/src/{preview.rs,fleet/stream.rs,fleet/bridge_wasm.rs}`.
