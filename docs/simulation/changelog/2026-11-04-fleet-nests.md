# 2026-11-04 — Drone nests the agent places, and the simulation-only fleet exception (#drone-fleet 1/5, PR #116)

- New manifest element `drone_nest` (`id`, `position_enu`, `yaw_deg`, `drones` 1–4). Its drones
  are `<id>-d1` … `<id>-dN` and share the scenario's id namespace.
- Placement rules, identical in the station (`simulation/fleet_nests.py`) and the renderer
  (`scene_manifest/fleet.rs`): within ±500 m and 0–60 m up, off water, not inside a building or
  solid box unless on its roof, centres 6 m apart, at most 8 nests, no taken drone id.
- The renderer draws each nest as a landing pad and publishes the `Nests` resource.
- `add_element` takes a `drone_nest` (`DroneNestElement`, `AddElementRequest.drone_nest = 8`);
  the scene-builder skill says when and how to place nests. `water.water_surfaces` is public.
- Preset `earthquake-fleet`: three nests, five drones, one nest on a roof.
- Scope amendment: `docs/architecture.md` §1/§2.3/§4.3, `AGENTS.md` and `README.md` allow the
  agent to task *simulated* drones on the simulation machine only; no write path to any real
  flight controller.
- Decided without review: spacing is horizontal distance; a water box with a collider is water;
  plain-colour pad materials; `remove_element` refuses a drone id.
- Left for the `#drone-fleet` sweep node (stack-shared, over 500 lines): `world.rs`,
  `simulation_tools.proto`, `scenario_manifest.py` — records under `*/docs/code-issues/`.
