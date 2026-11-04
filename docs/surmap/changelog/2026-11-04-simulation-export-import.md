# Export and import a simulation from the chat

**Date:** 2026-11-04
**Feature:** Survey agent / chat UI, simulation store

- **Export.** The simulation pane's Export downloaded the scenario as `<id>.surmap-sim.zip`
  (`GET /sim/export/<id>.zip`): `scenario.json` with the name, latest manifest and the record of
  every library asset it referenced (files, SHA-256s, licence), plus those files at their
  `library/…` paths — enough to import on a station that never fetched them.
- **Import.** The pane's Import posted a picked bundle to `POST /sim/import?into=<id>`, which
  stored it as that scenario's next version (without `into`, a new scenario under the bundle's
  name); the pane showed the version it became and the iframe reloaded. A bad zip, a hash
  mismatch, a path outside the library, a refused licence or a `library/…` file neither the
  bundle nor the station held was refused (400) before anything was written, and the reason
  showed in the pane. Behind the access gate; CORS for the chat's dev origin. Bodies over the
  kit's 4 MB request limit were refused with 413.
- **Stale edits refused.** The simulation tools remembered the version they last showed the agent
  per scenario (create, edits, `get_scenario`, `describe_scenario`); an edit when the scenario had
  moved on without them was `ABORTED`, naming both versions and telling the agent to read the
  scene again. A scenario the tools never showed was not refused.
- **`describe_scenario`.** A new tool listing what a scenario held — every element, model, fire,
  building fire and district with kind, detail, ENU position and behaviour flag, plus the weather
  in one line. Its messages started `simulation_contents.proto`, the first step of splitting the
  oversized `simulation_tools.proto`.
- **Code.** `surmap.simulation.scenario_bundle`, `surmap.simulation.scenario_contents`,
  `ScenarioStore.adopt` / `import_scenario` / `library_file`; `sim_routes.import_simulation`;
  `ChatPort.importSimulation`; `SimulationPane` Export / Import.
- **Tests.** pytest: 9 bundle, 7 route, 9 tool (stale guard + describe); Vitest: 4 component,
  2 chat-page.

Docs: [docs/agent.md](../../agent.md) (*Chat UI — Export / Import*).
