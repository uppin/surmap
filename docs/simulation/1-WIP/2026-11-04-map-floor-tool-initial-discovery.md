# Discovery: simulation agent tools

`SimulationTools` (proto/surmap/agent/v1/simulation_tools.proto) handlers in `surmap.agent.tools.simulation_handlers` edit versioned scenarios in `ScenarioStore` (SQLite + hashed library under `library/`). Every edit is a pure manifest function + `store.save`. Codegen: `scripts/gen_agent_rpc.py`. The store serves `library/...` paths to the simulation page on one origin.
