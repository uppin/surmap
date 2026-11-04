# Initial Discovery: dev.sh ensures the simulation prerequisites

**Changeset**: [2026-11-04-dev-sim-prereqs.md](./2026-11-04-dev-sim-prereqs.md)
**Date**: 2026-11-04
**Passes**: 1

## Combined Conclusions

- `scripts/dev.sh` starts cm5, station, agent and chat. The agent command is
  `uv run python -m surmap.agent --sam-fake` — no `--sim-dist`, so the agent server
  answers `/sim/` with 404 (`src/surmap/agent/server/sim_routes.py`: `/sim/` answers
  404 without `page_dist`). The relative URL the agent reports
  (`src/surmap/agent/tools/simulation_core.py`: `scenario_url` → `/sim/?scenario=<id>`)
  therefore opens a black canvas at best.
- The checked-out build at `examples/bevy-sitl-poc/dist/` (gitignored) was built with
  trunk's default public URL `/`: its `index.html` imports `/bevy-sitl-poc-*.js` and
  fetches `/bevy-sitl-poc-*_bg.wasm` from the server root. Served under `/sim/` those
  requests 404 (browser console, 2026-11-04), the WASM never starts, and the canvas
  stays black. Verified live: `GET /sim/bevy-….js` → 200, browser's `GET /bevy-….wasm`
  → 404.
- The Bevy app itself is prefix-safe: assets resolve relative to the page
  (`AssetPlugin` default in `examples/bevy-sitl-poc/src/main.rs`), scenarios load as
  `scenarios/<id>.json` relative to the asset root
  (`examples/bevy-sitl-poc/src/shots.rs`: `manifest_path`), and the agent serves
  `/sim/assets/…` from `examples/bevy-sitl-poc/assets` plus the scenario store.
- Prerequisites inventory for the dev stack: `uv`, `yarn` (+ `web/agent-chat/node_modules`,
  already checked by `dev.sh`), `trunk` (only to build the sim page), the sim `assets/`
  dir, and a sim page build made with `--public-url /sim/`. Ports cm5/station/agent are
  out of scope: a taken port already stops the stack via the exiting service.
- Existing harness: `tests/test_dev_script.py` drives `dev.sh` through
  `SURMAP_DEV_<NAME>_CMD` overrides and `--dry-run` command planning; new tests follow it.

## Exploration 1: Why /sim/ is a black canvas — 2026-11-04

**Agent**: parent Grep/Glob/Read + live curl/browser-console evidence
**Scope**: `scripts/dev.sh`, `src/surmap/agent`, `examples/bevy-sitl-poc`, `tests/test_dev_script.py`

### Sequence

1. Read `scripts/dev.sh` — service commands, env overrides, existing node_modules check.
2. Grep `/sim`, `scenario=`, `sim-dist` in `src/`, `web/`, `docs/` — who serves the page.
3. Read `src/surmap/agent/server/sim_routes.py`, `src/surmap/agent/__main__.py`,
   `src/surmap/agent/tools/simulation_core.py` — serving rules and the reported URL.
4. Read `examples/bevy-sitl-poc/dist/index.html`, `index.html`, `README.md`, `.gitignore` —
   the build's public URL and how it was produced.
5. Live probes: `curl` the page, JS, WASM and scenario JSON under `/sim/`; browser console
   errors supplied by the developer (`GET /bevy-…_bg.wasm` → 404).
6. Read `tests/test_dev_script.py` — the existing fake-service/dry-run test harness.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|---|---|---|---|
| Grep | `sim-dist` | `src/surmap/agent` | `__main__.py:87` flag; `server/app.py:203` `sim_dist` |
| Grep | `/sim` | `src/surmap/agent/server` | `sim_routes.py:5-8` serving table; `:107` 404 without `page_dist` |
| Grep | `scenario=` | `src`, `web`, `docs` | `simulation_core.py:51` `scenario_url` |
| Grep | `trunk\|public-url\|sim-dist` | `examples/bevy-sitl-poc/README.md` | `trunk build index.html --release`, standalone `http.server -d dist` |

### Inspected files

#### `scripts/dev.sh`

**Why**: what the dev stack starts and which prerequisites it already ensures.
**Excerpt**: `CMD_agent="${SURMAP_DEV_AGENT_CMD:-exec uv run python -m surmap.agent $AGENT_ARGS}"` with `AGENT_ARGS="--sam-fake"`; the only prerequisite check is `web/agent-chat/node_modules`.

#### `examples/bevy-sitl-poc/dist/index.html`

**Why**: the URLs the browser actually requests.
**Excerpt**: `import init from '/bevy-sitl-poc-e758e12e6eb146ca.js'` and `module_or_path: '/bevy-sitl-poc-e758e12e6eb146ca_bg.wasm'` — root-absolute, built for `/`.
