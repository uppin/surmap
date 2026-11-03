# Survey agent tools and chat are a proto service with generated tool contracts

**Date:** 2026-11-03
**Feature:** Survey agent / tool contracts (`#survey-agent` 1/9, PR #76)

- **Protos.** New package `surmap.agent.v1`: `SurveyTools` (8 tools:
  demos, runs, SAM, objects, geometry, frames), `AgentJobs` (4 job tools),
  `ChatService` (6 rpcs streaming `TurnEvent`s) and the
  `default_execution` method option. Codegen:
  `scripts/gen_agent_rpc.py` writes the checked-in bindings and a
  descriptor set with source info into `src/surmap/agent/proto/`, with
  `.pyi` stubs fixed for mypy strict (including the typed extension handle).
- **Contracts.** `surmap.agent.contracts.tool_contracts` gives each tool
  rpc a `ToolContract`: snake_case name, the rpc comment as description,
  a JSON Schema 2020-12 for its arguments, and its default execution.
  Every schema carries an optional injected `execution` argument;
  `resolve_execution` merges a model override onto the default.
- **Services.** `surmap.agent.services` mounts the three services as
  `ServiceModule`s; an rpc with no handler answers `UNIMPLEMENTED`.
  Handlers, the job runner and the serving process come in later stack
  nodes.
- **Tests.** `tests/test_agent_contracts.py` (23) and
  `tests/test_agent_services.py` (9).

Docs: [docs/agent.md](../../agent.md).
