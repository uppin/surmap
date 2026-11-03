# Initial Discovery — Fireworks chat models for the survey agent

## Combined Conclusions

- **Two providers exist** in `src/surmap/agent/llm/`: Muse (`meta.py`, a SurMap `BaseChatModel`
  over the Meta Responses API with a fakeable `post_json` transport, a `usage_sink` and a
  `before_call` hook) and Ollama (`ollama.py`, `langchain-ollama`'s `ChatOllama`, listed from
  `GET /api/tags` through a one-method GET seam). Neither speaks OpenAI chat completions.
- **The registry** (`registry.py`) lists `meta:` when `MODEL_API_KEY` is set and `ollama:` from the
  loopback server; ids split at the first colon; `build` refuses any other provider with
  `UnknownModelProvider`. It reads an injected `environ` (default `os.environ`), so tests never
  touch the process environment.
- **Server wiring** (`server/app.py` `default_model_factory`): a `MetaResponsesChatModel` is
  copied with `before_call=ledger.check` and `usage_sink=ledger`; every other model is returned
  as built. `ListModels` returns `registry.available()`; `--model` (`__main__.py`) takes any id.
- **Usage ledger** (`usage.py`): `UsageLedger(record)` appends JSONL and keeps per-provider
  totals; `check(provider)` raises `BudgetExceeded` from `SURMAP_BUDGET_<PROVIDER>_{CALLS,TOKENS}`.
  Provider `fireworks` gets `SURMAP_BUDGET_FIREWORKS_*` for free.
- **The runtime streams**: `runtime/graph.py:_stream_reply` calls `model.astream(...)` and adds
  `AIMessageChunk`s, so a provider must be correct on the streaming path (`_astream`), not only
  `_generate`. Tool calls arrive as `tool_call_chunks` and are merged by chunk addition.
- **Web**: the model picker renders whatever `ListModels` returns (`web/agent-chat`), so a new id
  prefix needs no web change.
- **Fireworks** serves an OpenAI-compatible chat completions API at
  `https://api.fireworks.ai/inference/v1` (`POST /chat/completions`, `GET /models`), Bearer key,
  OpenAI `tools` / `tool_calls`, SSE streaming with `stream_options.include_usage`. Model ids are
  paths with slashes: `accounts/fireworks/models/<name>`.
- **`langchain-openai` 1.7.3** (with `openai` 3.x) ships `py.typed`; a `ChatOpenAI` subclass that
  overrides `_generate` / `_agenerate` / `_stream` / `_astream` passes `mypy --strict` (checked in
  a throwaway module). `ChatOpenAI` holds the key as `SecretStr` (`repr` masks it), accepts
  `base_url`, `stream_usage`, `max_retries`, `use_responses_api`, and its own `http_client` /
  `http_async_client`. `openai` errors: `APIStatusError` (with `status_code`; `AuthenticationError`
  for 401), `APIConnectionError`, `APITimeoutError`.
- **Real-socket test host**: `surmap.rpc.hosts.hypercorn.HypercornHost(ServerDescription(
  http_routes=(HttpRoute(method, path, handler),)), None, port=0)` serves async
  `HttpRequest → HttpResponse` handlers (`rpc/http.py`); `tests/test_agent_server_e2e.py` already
  runs the agent that way. A whole-body `text/event-stream` response is a valid SSE stream for the
  OpenAI client.
- **Deferred work cross-check**: `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/` hold
  nothing about model providers or the registry.
