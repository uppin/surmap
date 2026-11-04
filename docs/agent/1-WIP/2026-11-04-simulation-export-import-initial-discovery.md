# Initial discovery: export and import a simulation from the chat

**Date**: 2026-11-04
**Changeset**: [2026-11-04-simulation-export-import.md](./2026-11-04-simulation-export-import.md)

## What exists

- **Chat pane.** `web/agent-chat/src/components/SimulationPane.tsx` shows the scenario the
  conversation created (derived from the transcript by `view-model/simulation.ts`): name,
  version, credits, the live `/sim/?scenario=<id>` iframe keyed by `id:version`. No actions.
- **Store.** `surmap.simulation.scenario_store.ScenarioStore` (SQLite + hashed library):
  `create_scenario`, `save` (validates and appends a version), `scenario`, `asset`, `assets`,
  `download` (licence-checked, files hashed under `library/<source>/<asset id>/`). A manifest
  references library files by `library/…` paths (`_referenced_paths`: model `glb`, material maps)
  and the PoC's shipped assets by other relative paths.
- **HTTP.** `surmap.agent.server.routes.agent_http_routes`: one `GET *` handler that serves the
  page, then `/sim/` (`sim_routes.serve_simulation`), then datasets/frames/geometry; only
  `POST /auth/session` is a plain POST. The access gate guards every GET except `/health` and
  the page. `/sim/` responses carry no CORS headers.
- **Agent tools.** `SimulationTools` (`proto/surmap/agent/v1/simulation_tools.proto`, over the
  500-line limit — `src/surmap/docs/code-issues/oversized-file-simulation-tools-proto.md`). All
  edits go through `simulation_core.edit_scenario` (read latest → edit → `store.save`), so an
  edit always applies to whatever the latest version is, even one the agent never saw.
  `GetScenario` returns the raw manifest JSON; nothing summarises what a scene holds.
- **Tooling lifetime.** `simulation_tool_handlers` builds one `SimulationTooling` per server,
  shared by every conversation and subagent; handlers get no conversation id.

## Findings that shape the change

1. A manifest is only portable with the library files it references; another station has
   never downloaded them, so an export must carry them (and their licence records).
2. The only out-of-band writer will be the import route; every agent write already funnels
   through `edit_scenario`, which is the one place to refuse a stale edit.
3. Because handlers have no conversation context, "what the agent last saw" is tracked on the
   shared tooling, per scenario.
4. `simulation_tools.proto` is oversized; new messages go in a new imported proto file.
