# Initial discovery — agent skill support

## Combined conclusions

- The agentic chat's tools are proto-driven: `proto/surmap/agent/v1/*.proto` rpcs become
  `ToolContract`s via `surmap.agent.contracts.tool_contracts`, are bound to handlers by
  `surmap.agent.server.binding.agent_tools`, and run as jobs through
  `surmap.agent.runtime.jobs.JobRunner` under an `ExecutionPolicy`
  (`src/surmap/agent/runtime/tools.py`: `BoundTool`, `bind_contract_tool`, `job_tools`).
- The turn loop is `surmap.agent.runtime.graph.build_turn_graph` (model ⇄ tools, round cap,
  repeated-failure cut-off); `AgentSession` (`runtime/session.py`) owns history, steering and
  job notices. `ChatHub` (`server/hub.py`) creates one session per conversation with a
  `ToolFactory = Callable[[JobRunner], Sequence[BoundTool]]`.
- `build_agent_description` (`server/app.py`) assembles contracts from `SurveyTools`,
  `MapTools` and `AgentJobs`, builds the hub with `SYSTEM_PROMPT`, and mounts the services.
  Adding model-facing tools that are not proto rpcs means constructing `ToolContract`s
  directly and appending their `BoundTool`s in the hub's tool factory — no codegen needed.
- The map tools (`MapTools`, 12 rpcs) edit a display-only `MapSceneStore`
  (`tools/map_handlers.py`, `tools/map_layers.py`): GLB objects, camera, drawn routes,
  layer catalogue. Positions are WGS84 lon/lat; routes need ≥ 2 waypoints; every change
  bumps the scene `revision` the chat UI polls. Passive survey only: routes are drawn
  paths, never flight plans.
- An external reference implementation of agent skills was studied for its loading design:
  a directory per skill holding `SKILL.md` with `name`/`description` front matter; a
  catalogue that lists name+description only and loads one body at a time (so bodies cost
  context only when chosen); builtin tree plus an overlay root that wins on name collision;
  a 64 KiB body cap (refuse, never truncate); skill names guarded against escaping the
  skills directory (anchored check plus post-`resolve()` containment); a missing directory
  lists nothing while no configured root at all is an error. This changeset adopts that
  design in SurMap's own shape; the reference is not named anywhere in shipped code or docs.
- `pyyaml` exists only as a transitive entry in `uv.lock`, not a declared dependency, so
  front matter is parsed with a small scalar parser instead of adding a dependency.

## Exploration 1 — SurMap agent wiring and the reference skill design

1. Read `AGENTS.md`, the `tdd`, `pr-lifecycle`, `fluent-tests` and `analyze-third-party`
   skills and their references (changeset template, fluent pytest guidance).
2. Listed `src/surmap/agent/` (`contracts.py`, `runtime/{graph,session,jobs,tools,events}.py`,
   `server/{app,hub,binding,chat_service}.py`, `tools/{handlers,map_handlers,map_layers,workspace}.py`)
   and read each wiring point named in the conclusions.
3. Read `proto/surmap/agent/v1/map_tools.proto` and `survey_tools.proto` for the tool
   catalogue the first skill must teach, and `docs/agent.md` for the documented contracts.
4. Studied the reference project's skill catalogue, its `list_skills`/`load_skill` tool
   shape (`{"skills": [{name, description}]}` / `{"name", "body"}`), its builtin+overlay
   rooting and its staging of a shipped skills tree; distilled the design properties above.
5. Checked `pyproject.toml`/`uv.lock` for a YAML dependency and `tests/agent_fakes.py`,
   `tests/test_agent_server_app.py` for the fluent test seams (`ScriptedChatModel`,
   `InMemoryHost`, fake workspaces) the red tests will use.
