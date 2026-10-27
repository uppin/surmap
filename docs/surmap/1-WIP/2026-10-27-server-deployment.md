# Changeset: Server deployment — entrypoints, SSH deploy scripts, systemd units

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package, entrypoint wiring + shell/systemd artifacts, no new service behaviour

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/` — neither exists
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Stub API — `build_description` in both entrypoint modules (`TODO(pr-6)`)
  - [ ] Create failing acceptance tests
  - [ ] Run acceptance tests (verify they fail)
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `cm5_main` / `station_main` entrypoints on `HypercornHost`
  - [ ] `deploy-cm5.sh` / `deploy-station.sh` (source path + SSH target as CLI args) + `deploy-lib.sh`
  - [ ] systemd units + `docs/deployment.md`
  - [ ] Acceptance: entrypoint/script tests pass; a local socket smoke of both servers
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/architecture.md` §10 — deployment path named

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-27-server-deployment-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: new `src/surmap/survey/cm5_main.py`, `src/surmap/survey/station_main.py`
- **repo tooling**: `scripts/deploy-cm5.sh`, `scripts/deploy-station.sh`, `scripts/deploy-lib.sh`, `deploy/systemd/*.service`, `docs/deployment.md`

## Summary

Adds runnable entrypoints for both survey servers and their SSH +
systemd deployment: sync, install unit, restart, verify active.

## Background

The stack's servers (n4, n5) are libraries: service-module factories
with no process to run, no unit to install, and no way onto the CM5 or
the station. Deployment targets differ per developer and machine, so
the scripts take the source path and SSH target as CLI arguments and
commit no machine inventory.

## Scope

- **Implementation**: entrypoints; deploy scripts + shared lib; systemd units
- **Testing**: entrypoint description tests, script contract tests, local socket smoke

## Technical Changes

### State A (Current)

- No entrypoint, unit, or deploy script; servers only run in tests.

### State B (Target)

- `surmap.survey.cm5_main` / `station_main`: `build_description()` →
  `ServerDescription` (service module + health routes), `main()` parses
  `--host`/`--port`, serves via `HypercornHost` until signalled, stops
  cleanly. Defaults: CM5 `0.0.0.0:8080`, station `0.0.0.0:8081`.
  Both serve their in-memory adapters until hardware adapters exist.
- `scripts/deploy-cm5.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port]`
  (station likewise): rsync source → remote dir (default
  `/opt/surmap`), install deps there (`uv sync --no-dev`, falling back
  to a venv + `pip install .`), render + install the systemd unit
  (install dir/port substituted), create the `surmap` system user,
  `daemon-reload`, `enable`, `restart`, then require
  `systemctl is-active`. Usage + exit 2 when arguments are missing.
- `deploy/systemd/surmap-{cm5,station}.service`: `User=surmap`,
  `Restart=on-failure`, `ExecStart` on the entrypoint.

### Delta (What's Changing)

#### surmap

- **API**: two new process entrypoints; no service-contract change

## Verification

**Method:** V1 fail→pass for entrypoints; V3 (deterministic inspection) for scripts/units, whose real target machines do not exist in CI
**Command:** `uv run pytest -q tests/test_survey_entrypoints.py tests/test_deploy_scripts.py` and `bash -n scripts/deploy-cm5.sh scripts/deploy-station.sh scripts/deploy-lib.sh`
**Before:** tests fail (entrypoint modules missing / stubs); scripts absent
**After:** tests pass; a local smoke serves `/health/is_alive` from both entrypoints on ephemeral ports

## Testing Plan

**Primary Test Approach:** Integration — build each description and
serve it in-process (`InMemoryHost`) asserting service + health route;
script contract tests read the scripts and pin the CLI/restart
contract. One manual local socket smoke of `python -m` per server,
recorded in the Green row.

## Acceptance Tests

### surmap

- **Integration**: `tests/test_survey_entrypoints.py` — both descriptions serve service + health
- **Unit**: `tests/test_deploy_scripts.py` — usage guard, argument order, restart-last contract

## Inherited Dependencies — do not implement here

Symbols this PR builds on that a **predecessor owns**. They arrive as stubs; implementing them here
would collide with the PR that owns them.

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `cm5_service_module` (#10) | n4 | implemented (green, pushed) | mounts it in a description; never edits `cm5_server.py` |
| `station_service_module` (#11) | n5 | implemented (green, pushed) | mounts it; never edits `station_server.py` |

**Greenable independently?** no — needs n4 (#10) and n5 (#11) green first; both are green, so this layer is startable now.

## Stack Context

**Stack**: Survey streaming · slug **`#survey-stream`** — this PR is **6 of 6** · #pending
**Branch**: `pr-6-server-deployment` · **Base**: `pr-5-station-sam-server`
**Successor**: none — top of stack
**Kind**: Feature · behaviour-adds — `(Type: Feature, Behaviour: adds)`
**Workflow**: preset `feature` · planned by `/add-to-pr-stack` · pass-2 = owned stubs + failing acceptance tests

Why the boundary falls here: running and deploying the servers is a
seam of its own; the services it starts are owned below it.

### Owned API surface

- `surmap.survey.cm5_main`, `surmap.survey.station_main` (`build_description`, `main`)
- `scripts/deploy-cm5.sh`, `scripts/deploy-station.sh`, `scripts/deploy-lib.sh`
- `deploy/systemd/surmap-cm5.service`, `deploy/systemd/surmap-station.service`

### Green wave

**Wave:** 3 of 3
**Node:** n6 — this PR's position in the stack
**Concurrent with:** none — this node is alone in its wave
**Blocks:** nothing

Real dependency edges, as opposed to the branch line:

    n4 (#10) → n6      n5 (#11) → n6

### Greenable independently?

**no — blocked by n4 (#10), n5 (#11)**: its entrypoints mount their
service modules. Both are green and pushed, so the layer is startable
now (ancestors rebased in before Green, per the stack gate).

### Trunk-merge safety

**When this PR merges alone:** production deploy/runtime and local dev
workflows stay working (`uv run pytest -q`, `uv run mypy`; entrypoints
are inert until run, scripts until invoked). **Local dev data:** no.
**Production data:** none.
