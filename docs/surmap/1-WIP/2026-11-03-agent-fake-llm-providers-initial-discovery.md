# Initial discovery: Muse and Ollama on fake provider servers

**Changeset**: [2026-11-03-agent-fake-llm-providers.md](2026-11-03-agent-fake-llm-providers.md)

## Seams found

| Provider | Real client | Base-URL seam | Notes |
|---|---|---|---|
| Fireworks | `ChatOpenAI` → `openai` → `httpx` | `SURMAP_FIREWORKS_URL` / `base_url` | already on a fake server (#87) |
| Muse | `UrllibMetaMuseTransport` (stdlib `http.client`, no redirects) | `MetaResponsesChatModel.base_url`; **none on the registry** | loopback `http` allowed by the transport |
| Ollama chat | `ChatOllama` → `ollama` 0.6.3 → `httpx` | `SURMAP_OLLAMA_URL` / `base_url` | `stream` defaults to `true` (NDJSON); `stream=False` kwarg sends a whole reply |
| Ollama tags | `UrllibOllamaTagsTransport` (stdlib, 2 s) | `SURMAP_OLLAMA_URL` | an unreachable server lists nothing |

Wire formats used by the stubs: Meta Responses `POST /v1/responses` whole JSON (`output` items
`reasoning` / `message` with `output_text` parts / `function_call` with `call_id`, `name`,
JSON-string `arguments`; `usage.input_tokens`, `output_tokens`,
`output_tokens_details.reasoning_tokens`). Ollama `POST /api/chat` newline-delimited
`{model, created_at, message: {role, content, tool_calls?: [{function: {name, arguments: {…}}}]},
done, done_reason?, prompt_eval_count?, eval_count?}`; `GET /api/tags` `{models: [{name, model, …}]}`.

## Baseline (16c917b)

72 collected test titles across `tests/test_agent_llm_meta.py` (27 incl. 1 live),
`tests/test_agent_llm_registry.py` (23 incl. 1 live), `tests/test_agent_server_app.py`,
`tests/test_agent_server_e2e.py`. Coverage of `surmap.agent.llm` from those plus the Fireworks
suite: 84 % (fireworks 82, meta 91, ollama 55, registry 100).

## Cases using fake transports (to replace)

- `test_agent_llm_meta.py` — 12 model-level cases through `RecordingMetaTransport` (tool binding ×2,
  endpoint, effort/cap, bearer, missing key, tool call, ledger, budget, empty retry, two empties,
  async). 14 pure mapping cases stay as unit tests.
- `test_agent_llm_registry.py` — 8 cases through `FakeOllamaTags` / `RecordingMetaTransport`;
  Ollama build cases checked only attributes.
- `test_agent_server_app.py` — 2 Muse cases (budget gate, ledger) through `RecordingMetaTransport`;
  `FakeOllamaTags` in 4 registry builders.
- `test_agent_server_e2e.py` — `FakeOllamaTags("scripted")` in the registry builder.

The old → new title mapping is written here at the Green row.
