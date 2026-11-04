# Changeset: Export and import a simulation from the chat

**Date**: 2026-11-04
**Status**: ✅ Complete
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — two packages (`surmap` server + tools, `web/agent-chat`), a new proto file and rpc, a new HTTP surface, a store extension

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + companion
  - [x] Classify (Feature · adds), place in `docs/agent/1-WIP/`
  - [x] Discovery companion written
  - [x] User decisions recorded (bundle format / agent reads / stale edits refused)
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests · pytest 22 red on missing implementation (3 guards already green); vitest 6 red
  - [x] Bundle round trip: export → import on a fresh store, library files and licences carried
  - [x] Import refuses a tampered, path-escaping or incomplete bundle
  - [x] HTTP: `GET /sim/export/<id>.zip`, `POST /sim/import?into=<id>`
  - [x] Tools: an edit after an out-of-band version is refused as stale; a read clears it
  - [x] Tools: `describe_scenario` lists what the scene holds
  - [x] Web: pane Export link, Import picker, pane shows the imported version
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · 25 new pytest + 6 new vitest green; ruff, mypy, typecheck, lint, build green
  - [x] `surmap.simulation.scenario_bundle` (export / import) + store support
  - [x] HTTP routes
  - [x] Stale-edit guard in `SimulationTooling` / `edit_scenario`
  - [x] `DescribeScenario` rpc (messages in `simulation_contents.proto`), regenerated bindings
  - [x] Chat port `importSimulation`, pane buttons, ChatPage wiring
  - [x] `creating-a-simulation` and `building-a-simulation-scene` skills name `describe_scenario` and the stale refusal
- [wf 4] ✅ 2026-11-04 `/pr-wrap` Wrap — validate, clean up, verification, docs · docs/agent.md + changelog `docs/surmap/changelog/2026-11-04-simulation-export-import.md`; 1-WIP deleted
  - [x] Verification executed — result recorded
  - [x] `docs/agent.md` — Simulation pane section names Export / Import
  - [x] Code-issue record for `simulation_tools.proto` measurement updated

## Initial Discovery

Full exploration: [2026-11-04-simulation-export-import-initial-discovery.md](./2026-11-04-simulation-export-import-initial-discovery.md).

## Decisions (user, 2026-11-04)

- **Format**: a zip bundle — name, latest manifest, and every library asset the manifest
  references (files + licence records), so it imports on a station that never fetched them.
- **After import**: the agent is not messaged; it learns the scene through tools — it gets a
  tool to learn what the simulation contains (`describe_scenario`) besides `get_scenario`.
- **Stale knowledge**: an agent edit based on a version older than the latest (e.g. after an
  import) is refused with an error telling it to re-read the scenario first.

## State A

The simulation pane only displays the scenario. A scene cannot leave the station or come back,
and agent edits always apply to the latest version, even one the agent never saw.

## State B

- The pane has **Export** (downloads `<id>.surmap-sim.zip`) and **Import** (pick a bundle; it is
  saved as the next version of the pane's scenario, the pane shows the new version and the
  iframe reloads). An import error shows in the pane.
- `GET /sim/export/<id>.zip` → `application/zip` attachment. `POST /sim/import?into=<id>` with
  the zip body → `{"scenario": {id, name, version, url, credits}}`; without `into` a new scenario
  is created under the bundle's name. A bad bundle is 400, an unknown `into` 404. Both go
  behind the access gate and carry CORS for the chat's dev origin.
- Bundle: `scenario.json` (`format: "surmap-scenario-bundle"`, `format_version: 1`, name,
  manifest, asset records with each file's path/SHA-256/bytes) plus `library/…` files. Import
  checks every hash, keeps paths inside the library, refuses licences `check_licence` rejects,
  and refuses a manifest whose `library/…` paths neither the bundle nor the station holds.
- Simulation tools remember the version they last showed per scenario (create, edit,
  `get_scenario`, `describe_scenario`; not `get_behaviour`, which shows one tree only). An edit when the latest version is
  newer than that is `ABORTED`: "scenario … is at vN but you last saw vM … call
  describe_scenario or get_scenario, then redo the edit". A scenario the tools never showed is
  not refused.
- `describe_scenario(scenario_id)` → id, name, version, url, credits, weather line, and one
  item per element / model / fire / building fire / district: id, kind, a short detail, ENU
  position when it has one, whether it has a behaviour.

## Delta

- New `src/surmap/simulation/scenario_bundle.py`, `scenario_contents.py`; `ScenarioStore`
  gains `adopt_asset` and `import_scenario`.
- `sim_routes.py` + `routes.py`: export / import routes.
- `simulation_core.py`: seen-version guard; `simulation_handlers.py`: `DescribeScenario`.
- `proto/surmap/agent/v1/simulation_contents.proto` (new) + one rpc in `simulation_tools.proto`.
- Web: `ports.ts` `importSimulation`, `connect-chat.ts`, `SimulationPane.tsx`, `ChatPage.tsx`.

## Known limits

- Request bodies are capped at 4 MB for every route (`surmap.rpc.http_limits`); a larger bundle
  is refused with 413 and the pane says so. Raising it per route is a kit change, not made here.
- The seen-version memory is per server (tool handlers get no conversation id), shared by every
  conversation and subagent, and lost on restart (then nothing is refused until the next read).
- Import is offered only inside the pane, i.e. into the conversation's simulation.

## Verification

V1 — executable tests.

- Red (before implementation): 22 new pytest failed on the missing module/handler/routes (3
  regression guards already held); 6 new vitest failed on the missing pane controls.
- `uv run pytest -q`: 2463 passed, 38 skipped; the files touched by the last edits re-run after
  them: 88 passed. `ruff check`, `ruff format --check`, `mypy` (strict): green.
- `yarn test --run`: 159 passed / 16 files. `yarn typecheck`, `yarn build`: green. `yarn lint`:
  green (2 pre-existing warnings in `src/components/ui/`).
- Not done: `yarn e2e` (no e2e added; the stub server has no `/sim/import`) and a manual run
  against a live station.
