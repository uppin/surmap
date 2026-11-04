# 2026-11-04 — The survey agent flies the simulation's fleet (#drone-fleet 4/5, PR #120)

- `FleetTools` (`proto/surmap/agent/v1/fleet_tools.proto`, eight rpcs, each SYNC · 10 s · FAIL)
  is the agent's surface on a running simulation, registered only with a `SimulationRig` beside
  `SimulationTools`: `list_nests`, `list_drones`, `launch_drone`, `set_route`, `add_detour`,
  `recall_drone`, `set_active_drone`, `get_fleet_log`.
- `fleet_tool_handlers(store, registry)` resolves the scenario through the store first (unknown
  → `NOT_FOUND` for every rpc), reads nests from the scenario's latest manifest, and sends
  commands through the scenario's `FleetController`. Its errors map to Connect codes: unknown
  drone `NOT_FOUND`, other `FleetInvalid` `INVALID_ARGUMENT` (`<rule>: <message>`), `FleetRefused`
  `FAILED_PRECONDITION` (the page's reason verbatim), `FleetUnavailable` `UNAVAILABLE`,
  `FleetTimeout` `DEADLINE_EXCEEDED`. `get_fleet_log` returns the scenario's own session as the
  `--fleet-log` replay file. Commands answer `FleetCommandResult { seq, at_s }`.
- The `flying-the-fleet` skill teaches the sortie (plan ENU routes clear of buildings, 5–60 m
  up, ≤ 8 m/s; launch, detour, re-route, switch the active drone, recall, read the log), and the
  SYSTEM_PROMPT and `using-the-map` now name the simulation-only exception: simulated drones can
  be tasked, real aircraft are never commanded.
- Follow-ups recorded: mirroring fleet routes and drone markers onto the chat map
  (`src/surmap/docs/todo/2026-11-04-fleet-routes-on-chat-map.md`), and a `sim_t_s` on
  `ListDronesResponse` when the controller exposes a telemetry time.
- Verification: V1 — `uv run pytest -q tests/test_agent_fleet_tools.py
  tests/test_agent_fleet_tools_e2e.py` 49 passed; full gates green (ruff check/format, mypy
  529 files, pytest 2361 passed / 38 skipped).
