# Changeset: dev.sh ensures the simulation prerequisites

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Bug Fix
**Behaviour**: changes
**Complexity**: 2 — one shell script + its pytest harness, integration-level tests with fake services

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset (no PRD: not user-visible beyond the dev stack), initial discovery · this file + discovery companion
  - [x] Discovery companion written from the live black-canvas investigation
  - [x] State A / State B / Delta and Verification written
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — reproduction tests, committed · 4 red, 1 preservation-green @ `tests/test_dev_script.py` (`-k sim`: no `--sim-dist`, no build, no refusal)
  - [x] Dry-run test: the agent command serves the sim page (`--sim-dist`)
  - [x] Test: a missing or root-built sim page is rebuilt via a stubbed `trunk`
  - [x] Test: a `/sim/`-built page is left alone (no rebuild)
  - [x] Test: a missing `trunk` fails with an install hint before any service starts
- [wf 3] ✅ 2026-11-04 `/green` Green — fix until the reproduction passes · 14 passed in `tests/test_dev_script.py`; live sim renders (see Verification)
  - [x] `dev.sh` passes `--sim-dist` to the agent by default (`SURMAP_DEV_SIM_DIST` override)
  - [x] `dev.sh` builds the sim page with `trunk build --public-url /sim/` when missing or built for `/`
  - [x] `dev.sh` checks `uv` / `yarn` / sim assets up front with actionable messages
  - [x] `dev.sh` fetches the pinned sim assets (`scripts/fetch_sim_assets.py`) before starting
  - [x] Live check: `/sim/?scenario=house-and-tree` loads its WASM (200) and renders
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [x] Verification executed — result recorded
  - [ ] `docs/simulation/bevy-simulation.md` — dev-stack serving note updated
  - [ ] Full gates green: `ruff check`, `ruff format --check`, `mypy`, `pytest`

## Stack Context

**Stack**: sim dev stack · slug **`#sim-dev`** — this PR is **1 of 2**
**Branch**: `fix/dev-sim-prereqs` · **Base**: `main`
**Successor**: `feat/sim-trackpad-ptz` — trackpad PTZ for the chase view
**Kind**: Bug Fix · changes — the `(Type, Behaviour)` pair from the header
**Workflow**: preset `bugfix` · planned by `/plan-red`

### Owned API surface

`scripts/dev.sh` prerequisite behaviour and its harness in `tests/test_dev_script.py`.

### Green wave

**Wave:** 1 of 1
**Node:** n1
**Concurrent with:** none
**Blocks:** n2 (branch base only; no behaviour dependency)

### Greenable independently?

**yes** — it owns everything its tests drive.

### Trunk-merge safety

**When this PR merges alone:** local dev workflows stay working (`./scripts/dev.sh`,
`uv run pytest -q` green). **Local dev data:** may fetch pinned sim assets on first
run — regenerable, uncommitted. **Production data:** none.

## Initial Discovery

Full codebase exploration that grounded this plan: [2026-11-04-dev-sim-prereqs-initial-discovery.md](./2026-11-04-dev-sim-prereqs-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## State A

- `scripts/dev.sh` starts cm5, station, agent (`--sam-fake` only) and chat. Its only
  prerequisite check is `web/agent-chat/node_modules`.
- Without `--sim-dist` the agent server answers `/sim/` 404; with a dist built for `/`
  (trunk's default) the page loads but its root-absolute JS/WASM URLs 404 under `/sim/`,
  so the sim is a black canvas. The dist in the checkout is exactly such a build.

## State B

- `dev.sh` serves the simulation page by default: the agent command carries
  `--sim-dist <examples/bevy-sitl-poc/dist>` (`SURMAP_DEV_SIM_DIST` overrides the path).
  The sim page is ensured on every real run (not `--dry-run`), even with service-command
  overrides, so the test harness exercises the same prerequisite path.
- Before any service starts, `dev.sh` ensures the prerequisites: `uv` and `yarn` on
  PATH, chat `node_modules` (as today), the sim assets dir present, the pinned
  textures/models/HDRI fetched (`scripts/fetch_sim_assets.py`, idempotent), and a sim
  page whose `index.html` addresses its JS/WASM under `/sim/` — rebuilding it with
  `trunk build index.html --release --public-url /sim/` when it is missing or built
  for another prefix. A missing `trunk` or a failed fetch stops the script first.
- `--dry-run` only plans: it prints the new agent command and builds nothing.

## Delta

- `scripts/dev.sh`: agent default command, prerequisite checks, sim-page build step, usage text.
- `tests/test_dev_script.py`: reproduction tests (dry-run + stubbed-`trunk` runs).

## Verification

- `uv run pytest -q tests/test_dev_script.py` — red before the fix, green after.
- Full gates: `uv run ruff check src tests`, `uv run ruff format --check src tests`,
  `uv run mypy`, `uv run pytest -q`.
- Live: `./scripts/dev.sh` (alternate ports when 8080/8081 are taken), then
  `curl -o /dev/null -w '%{http_code}' 'http://127.0.0.1:8780/sim/?scenario=house-and-tree'`
  and the browser loads `/sim/bevy-…_bg.wasm` with 200 and renders the scene.

Executed 2026-11-04: `SURMAP_DEV_CM5_PORT=18080 SURMAP_DEV_STATION_PORT=18081 ./scripts/dev.sh`
(fetch step verified all 107 pins in-script), then every previously failing URL returned
200 — page, JS, 54 MB WASM, scenario JSON, `white_plaster_02_*` / `clay_roof_tiles_02_*`
textures and the HDRI. A browser-pane screenshot of
`http://127.0.0.1:8780/sim/?scenario=house-and-tree` shows the textured house-and-tree
scene (plaster walls, clay-tile roof, ground, HUD) with zero `ERROR`/`404` console lines.
