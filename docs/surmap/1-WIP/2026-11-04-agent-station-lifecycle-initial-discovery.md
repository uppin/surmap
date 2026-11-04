# Initial Discovery: agent station lifecycle — on-demand SAM GPU, tools, UI indicator

## Combined Conclusions

- **Tools are proto rpcs.** One rpc per tool in a `*Tools` service; leading comment = description;
  `option (default_execution)` = policy (`proto/surmap/agent/v1/execution.proto:20-40`). Handlers
  are `Mapping[str, Handler]` by rpc name (`agent/tools/handlers.py:104`); `build_agent_description`
  (`agent/server/app.py:245-310`) binds contracts + handlers as agent tools and mounts the same
  handlers over Connect for the UI. Optional services (SimulationTools) are mounted only when
  configured (`app.py:276-305`). Python gen: `scripts/gen_agent_rpc.py` (`PROTOS` tuple), service
  modules in `agent/services.py`; TS gen: `yarn gen` into `web/agent-chat/src/gen` (checked in).
- **The agent's SAM is fake only.** `build_demo_workspace` refuses without `--sam-fake`
  (`app.py:216`) and passes `CentredBoxVideoSamDetector()`; `DemoWorkspace` drives the detector
  with `reset(prompt)` / `track(frame)` (`agent/tools/workspace.py:227-232, 474-479`).
  TODO `src/surmap/docs/todo/2026-11-03-agent-cli-sam-flags.md` records the missing real-SAM path.
- **A station-backed `VideoSamDetector` exists.** `demo/remote.py:459` `RemoteSamDetector(address,
  prompt, token)`: one `StreamAnalysis` exchange per frame over a cached `SurveyConnection`
  (`_Link`), client-side IoU track ids, `close()` closes the link.
- **Modal SDK control surface (1.6.3, public API).** `Function.from_name(app, "serve",
  environment_name=…)`; `get_current_stats()` → `backlog`, `num_total_runners`,
  `num_running_inputs`; `update_autoscaler(min_containers=, scaledown_window=)` (2–3600 s; reset by
  the next deploy); `get_web_url()`. Stopping one container exists only through the private
  `client._stub.ContainerStop` — not used. Stats read no HTTP from the station, so a status poll
  cannot start or keep up a GPU; a health GET is an input and resets the scaledown window.
- **What holds a container up.** An open WebSocket is an active input. The station's socket is
  served by the generic `surmap.rpc` Hypercorn host (`station_main.py:76-88`), so an idle close
  there is an rpc-layer change; the agent closing its own link is what lets the station go down.
- **UI.** Header `web/agent-chat/src/ChatPage.tsx:204-234` (h1, server URL, nav, `ModelPicker`);
  `ChatPort` `src/ports.ts:118-136`; Connect adapter `src/adapters/connect-chat.ts:20-60`; tests:
  vitest `App.test.tsx` with `fakePort()`, component tests, Playwright `e2e/chat.spec.ts` over
  `e2e/stub-chat-server.ts` (Node Connect router).
- **CI never installs `modal`.** The modal app files are AST-tested; the SDK must stay out of the
  base dependencies (`modal-cloud` skill §0) and behind a typed protocol (AGENTS.md rule 5).

## Exploration 1: agent tools, SAM wiring, UI — 2026-11-04

### Sequence

Explore pass over `src/surmap/agent/**`, `proto/surmap/agent/v1`, `web/agent-chat/src`, docs
layout; follow-up reads of `app.py` (config, workspace, description), `__main__.py` (CLI),
`handlers.py` (binding), `demo/remote.py` (`RemoteSamDetector`, `_Link`), `survey/sam.py`
(`VideoSamDetector`), the Modal SDK reference (`Function.md`, `types.md`) and its CLI source
(`modal/cli/container.py:339`).

### Grep / glob

- `grep -rn "modal\|station" src/surmap/agent` — no Modal or remote-station use in the agent.
- `grep -rn "ContainerStop" <modal pkg>` — only `cli/container.py` and `_runtime`, via `_stub`.

### Inspected files

#### `src/surmap/agent/server/app.py`

`AgentServerConfig` (`:134-166`), `build_demo_workspace` (`:214-235`),
`build_agent_description` (`:245-310`) with the optional simulation mount.

#### `src/surmap/demo/remote.py`

`_Link` (`:63-131`) runs a private event loop thread, opens one `SurveyConnection` lazily;
`RemoteSamDetector` (`:459-560`).

### Findings

As in Combined Conclusions.
