# Initial discovery — simulation as a right-side pane inside the chat

## Conclusions

- The chat page is [web/agent-chat/src/ChatPage.tsx](../../../web/agent-chat/src/ChatPage.tsx):
  header, `MapPane` on top, then a grid `Transcript | JobsPanel` (16 rem right
  column), then `Composer` full width. No simulation UI exists in
  `web/agent-chat/src`.
- The agent creates simulations through `SimulationTools` (`proto/surmap/agent/v1/simulation_tools.proto`):
  `create_scenario` returns `ScenarioResponse { scenario: ScenarioInfo { id, name,
  version, manifest_json, credits, url, updated_at } }`, where `url` is
  `/sim/?scenario=<id>` (`scenario_url` in
  [simulation_core.py](../../../src/surmap/agent/tools/simulation_core.py:49)).
  Later scenario edits (`add_element`, `set_weather`, …) return the same
  `ScenarioResponse` shape at a bumped `version`.
- Tool results reach the chat transcript as `resultJson` on the finished tool
  item: `MessageToDict(..., preserving_proto_field_name=True)`
  ([binding.py](../../../src/surmap/agent/server/binding.py:98)) then
  `json.dumps` ([chat_service.py](../../../src/surmap/agent/server/chat_service.py:289)).
  So a `create_scenario` result is
  `{"scenario": {"id": …, "name": …, "version": …, "credits": […], "url": "/sim/?scenario=…"}}`.
- The canonical creation flow delegates to a subagent
  ([creating-a-simulation skill](../../../src/surmap/agent/skills/creating-a-simulation/SKILL.md)):
  the subagent's tool calls never appear in the main transcript
  ([subagents.py](../../../src/surmap/agent/subagents.py:9)); the main agent
  reports the scenario id, version and URL in its reply text. Detection must
  therefore also read the assistant's reported `/sim/?scenario=<id>` URL.
- `/sim/` is served by the same agent server
  ([sim_routes.py](../../../src/surmap/agent/server/sim_routes.py:87)), so an
  iframe at `<serverUrl>/sim/?scenario=<id>` works same-origin with the page.
- Frontend conventions: pure view-model under `src/view-model/`, components
  under `src/components/`, network only through `ChatPort` (`src/ports.ts`).
  This change needs no new network call: the transcript already carries
  everything, and `getConversation` replay restores it after a reload.
- Tests: Vitest + Testing Library, fluent builders in
  `src/test-support/` (`aConversation`, `aToolStep`). No `node_modules` in
  this checkout; install with `yarn local-install` (private registry).
