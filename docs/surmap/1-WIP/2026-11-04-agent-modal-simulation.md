# Changeset: The simulation on the deployed agent — the WASM page and its assets on Modal

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — one package (surmap survey hosting + the agent's Modal app), a filesystem preflight, unit and AST tests

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + companion; no PRD: the requirements are the developer's answers of 2026-11-04 (the deployed chat has the simulation, built from the latest WASM; the stereo bridge is a second PR)
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 8 new tests red at collection (`ImportError: SimBundleError`, `AGENT_SIM_ASSETS`); not yet committed — awaiting the developer's go-ahead
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · 25/25 in the two suites; full gates green
  - [x] `agent_command` passes `--sim-assets` and `--sim-dist` at the image's sim paths
  - [x] The agent image carries the built page and the assets with their pinned files
  - [x] `check_sim_bundle` refuses a missing or stale `dist/` and missing pinned assets; the app runs it at deploy time only
  - [x] Acceptance: `tests/test_modal_survey_apps.py` and `tests/test_modal_sim_bundle.py` pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [x] `docs/modal.md` — the agent row and its deploy steps: fetch the assets, `trunk build`, the preflight
  - [x] `docs/agent.md` — the deployed agent serves the simulation, without the bridge
  - [ ] (optional) Production readiness validated (3) — run if the diff reaches server code

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-04-agent-modal-simulation-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Summary

The deployed `surmap-agent` serves the Bevy simulation: the `trunk` build at `/sim/`, its assets
(the tracked JSON and the pinned CC0 files), and so the simulation tools, the chat's preview and
the `/sim/fleet` link through which the agent flies the drones. A deploy refuses to go ahead with a
`dist/` older than the page's sources or with pinned assets missing, so what is deployed is the
latest WASM.

## Background

The developer redeployed the agent from `main` at 329407b and expected the simulation with it
(2026-11-04): "the chat/agent app should also be deployed with latest WASM". The image never
carried the simulation, and the local `dist/` predated #142 and #144. The developer chose two
PRs: this one for the simulation, a second for the stereo bridge (same-port WebSocket, RTAB-Map
built natively into the agent image).

## Scope

- **Implementation**: `modal_hosting` sim paths and `check_sim_bundle`; `agent_command` flags;
  `modal_agent_app.py` image steps and deploy-time preflight.
- **Testing**: command, image-shape and preflight tests, all failing first.
- **Docs**: `docs/modal.md`, `docs/agent.md`; this changeset wrapped at the end.
- **Out of scope**: the stereo bridge on Modal (PR 2), building the WASM inside the Modal image,
  the CM5 and station apps.

## Technical Changes

### State A (Current)

- The agent image holds the chat page and `surmap` only. `agent_command()` passes no sim flags;
  the default `--sim-assets` is absent, so the simulation rig is off and `/sim/` answers 404.
- Nothing checks that a local `examples/bevy-sitl-poc/dist` is current.

### State B (Target)

- `modal_hosting` names `AGENT_SIM_ASSETS` and `AGENT_SIM_PAGE` (under `/opt/surmap/sim/`), and
  `agent_command()` passes them as `--sim-assets` and `--sim-dist`.
- The agent image adds `examples/bevy-sitl-poc/assets` and `examples/bevy-sitl-poc/dist` at
  those paths.
- `check_sim_bundle(poc_dir)` raises `SimBundleError`, naming the command that fixes it, when
  `dist/index.html` or a `.wasm` is missing, when the newest `.wasm` is older than any file under
  `src/`, `index.html`, `Cargo.toml` or `Cargo.lock`, or when a pin in `assets/assets.lock.json`
  has no file. `modal_agent_app.py` runs it when `modal.is_local()` (the deploy), not in the
  container.

### Delta

#### surmap (survey hosting, agent Modal app)

- **Implementation**: two path constants, two command flags, two image steps, one preflight.
- **API**: none; no proto or RPC change.

## Testing Plan

- `tests/test_modal_survey_apps.py`: the agent command parsed by the agent's CLI has
  `sim_assets == AGENT_SIM_ASSETS` and `sim_dist == AGENT_SIM_PAGE`; the image chain adds the
  page and the assets at those paths; the app calls `check_sim_bundle` behind `is_local()`.
- `tests/test_modal_sim_bundle.py`: a current bundle passes; a missing `dist/`, a `.wasm` older
  than a source file, and a missing pinned asset each raise `SimBundleError` naming the fix.

## Verification

**Method:** V1-fail→pass — the new tests fail on State A (no sim paths, no preflight), pass on State B; then a deploy to `ginas-bb` and `/sim/` checked live
**Command:** `uv run pytest -q tests/test_modal_survey_apps.py tests/test_modal_sim_bundle.py`, then the full gates (`ruff check`, `ruff format --check`, `mypy`, `pytest -q`)
**Before:** 2026-11-04 — `tests/test_modal_survey_apps.py` and `tests/test_modal_sim_bundle.py` fail at collection on State A (`ImportError: cannot import name 'SimBundleError'`) — the implementation is missing, not the environment
**After:** *(filled by the Wrap row)*

## Decisions & Trade-offs

- **Build locally, ship the output** — the same as the chat page's `yarn build`. Building the
  WASM inside the image would need a Rust toolchain in it and a full rebuild on every
  source change; the preflight stops a stale or missing build instead.
- **The pinned assets are uploaded, not fetched in the image** — fetching them in the image
  needs the fetch code before `add_local_python_source`, so every source change would refetch
  ~240 MB. Modal's local-dir sync uploads only changed files.
- **Staleness by mtime** — a fresh checkout or `git pull` touches the sources, which makes
  `dist/` look stale and forces a rebuild: it errs on the safe side.
