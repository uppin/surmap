# Initial Discovery: The simulation on the deployed agent

**Changeset**: [2026-11-04-agent-modal-simulation.md](./2026-11-04-agent-modal-simulation.md)
**Date**: 2026-11-04
**Passes**: 1

## Combined Conclusions

The deployed `surmap-agent` (`src/surmap/agent/modal_agent_app.py`) ships only the chat page
(`web/agent-chat/dist` → `AGENT_WEB_DIST`) and the `surmap` package. `agent_command()`
(`src/surmap/survey/modal_hosting.py`) passes no `--sim-dist` and no `--sim-assets`, and the
`--sim-assets` default (`examples/bevy-sitl-poc/assets`, relative to the working directory) is
not in the image, so `build_simulation_rig` returns None: no simulation tools, nothing at `/sim/`.

What the simulation needs on the agent, by part:

- **The page** — a `trunk build index.html --release` output in `examples/bevy-sitl-poc/dist`
  (gitignored, ~168 MB `.wasm`), served at `/sim/` by `serve_simulation` when
  `SimulationRig.page_dist` is set (`--sim-dist`).
- **The assets** — `examples/bevy-sitl-poc/assets`: tracked JSON (scene, cameras, districts, …,
  ~250 KB) plus the pinned CC0 textures, models and HDRIs (`assets.lock.json`, ~240 MB,
  gitignored, fetched by `scripts/fetch_sim_assets.py`, stdlib-only
  `surmap.simulation.sim_assets`). `build_simulation_rig` needs `scene.json`; the page fetches
  the rest from `/sim/assets/`.
- **The fleet link** — `/sim/fleet` is an ASGI WebSocket on the agent's own port
  (`fleet_routes.py`), and the page derives it from its own origin (`fleet/link.rs`:
  `wss://` for an `https:` page), so it already works through Modal's single web port.
- **The stereo bridge** — `serve_bevy_bridge` listens on a second port (`--bevy-bridge-port`)
  and each session starts a `StreamingRtabmapBackend` with no `native_binary`, i.e. Docker,
  which Modal containers do not run. It needs a same-port route and RTAB-Map built natively
  into the image (as `modal_cm5_app.py` does) — the developer split that into a second PR
  (2026-11-04).

Staleness is the risk the developer raised: the local `dist/` was built at 21:44, before #142
(21:46) and #144 (22:12) changed the page. The deploy has to refuse a `dist/` older than the
page's sources, and an assets dir missing pinned files, rather than ship them.

## Exploration 1: Modal agent app, sim serving and the page's sockets — 2026-11-04

- `modal_agent_app.py`: `image = debian_slim → uv_sync(--extra modal) → add_local_dir(web dist)
  → add_local_python_source(surmap)`; `serve()` runs `agent_command()`.
- `agent/__main__.py:103-116`: `--sim-assets` (default `DEFAULT_SIM_ASSETS`), `--sim-dist`,
  `--bevy-bridge-port`.
- `server/app.py:293-312` `build_simulation_rig`; `:321-357` `start_bevy_bridge`.
- `server/sim_routes.py:116-140` `serve_simulation`: scenarios from the store, library files,
  static assets, then the page from `page_dist`.
- `agent/tools/simulation_core.py:78`: the preview URL is the relative `/sim/?scenario=<id>`.
- `examples/bevy-sitl-poc/README.md`: `trunk build index.html --release`; `.gitignore:38-41`
  ignores `assets/{textures,models,hdri,scenarios}/`.
- `tests/test_modal_survey_apps.py`: agent command parsed by the agent's own CLI; app shape read
  with the AST (`image_steps`, `step_named`), since CI does not install `modal`.
