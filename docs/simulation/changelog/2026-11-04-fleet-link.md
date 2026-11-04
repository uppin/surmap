# 2026-11-04 — The fleet link: the station commands the running simulation's drones (#drone-fleet 3/5, PR #119)

- A page opened with `?fleet=1` links to the agent server's `/sim/fleet?scenario=<id>` WebSocket
  and speaks `fleet/v1`. The page sends `hello`, `applied`, `refused` and telemetry every 0.5 s.
  The station sends `command`. Goldens are in `tests/fixtures/fleet_link/`, and both the Python
  and the Rust codec re-encode them byte for byte.
- `surmap.simulation.fleet` holds the station's side:
  - typed commands (`Launch`, `SetRoute`, `Detour`, `Recall`, `SetActive`) whose JSON is the
    fleet log's;
  - `FleetController`, which validates (known drone, route, ±500 m, 5–60 m, 0.5–8 m/s, phase),
    then sends and waits 5 s for the page's answer, one request at a time;
  - `FleetRegistry` on `SimulationRig.fleet`, with one link per scenario (a second page closes
    with 4409, a protocol fault with 4400);
  - `FleetLogStore`, which adds `fleet_sessions` and `fleet_log` tables to the scenario store's
    SQLite file and exports a session as a `--fleet-log` file.
- The renderer gains `fleet/link.rs` (the pure codec, refusal texts, telemetry, `?fleet=1`
  parsing and the socket URL) and `fleet/link_wasm.rs` (the page's WebSocket, which drains
  commands into `FleetLog::push` at `SimClock::now()`). The `web-sys` features gain `WebSocket`,
  `MessageEvent`, `CloseEvent` and `ErrorEvent`. The banner and `Cargo.toml` no longer say that
  nothing is sent to a backend.
- `scripts/fleet_link_smoke.py` is a station for one browser tab that flies a scripted sortie
  and exports its log.
- Decided without review:
  - a drone the page just launched counts as flying until telemetry stamped at or after the
    launch arrives;
  - the page's `hello` list is the known-drone set while it is linked;
  - an `applied` that arrives after the timeout is still logged;
  - an unknown scenario closes with 4400.
- Wrap: `tests/test_sim_fleet_controller.py` (618 lines, created here) was split by subject into
  the controller (390), registry (152) and log-store (96) suites, with their shared builders in
  `tests/fleet_fakes.py`. No stack-shared file this PR touched reaches 500 lines.
- Verification: V1 (74 fleet pytest tests, `cargo test --locked link` 18) and V3 (the wasm check)
  passed. The developer deferred V4, the Chrome run, until after the stack merges ("please wrap
  n3. I'll do browser testing after the stack is merged", 2026-11-04):
  `src/surmap/docs/todo/2026-11-04-fleet-browser-verification.md`.
