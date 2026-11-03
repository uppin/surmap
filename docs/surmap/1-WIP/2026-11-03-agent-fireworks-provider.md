# Changeset: Survey agent — Fireworks chat models, and provider keys from `.env`

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one adapter over a stock OpenAI-compatible client (new runtime dependency), a real-socket fake provider, registry/server wiring, `.env` loading at three entry points; the external API is stable and widely used, so no unverified-protocol risk

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery + 1 deferred answer (commit 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 25 failing on own stubs, 3 guards passing, 1 live skipped — commit 2
  - [x] Fake Fireworks provider `tests/fake_fireworks.py` (real loopback socket, scripted rounds, recorded requests, JSON and SSE replies)
  - [x] Stubs with real signatures in `src/surmap/agent/llm/fireworks.py`; `langchain-openai` added to `pyproject.toml` / `uv.lock`
  - [x] Create failing acceptance tests
  - [x] Run acceptance tests (verify they fail)
  - [x] TDD Red — write failing unit/integration tests
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: `FireworksChatModel` — request, tool calls (whole and streamed), usage, budget gate, redacted errors
  - [ ] Milestone 2: registry — `fireworks:` listing (override → `GET /models` → built-in list) and `build`
  - [ ] Milestone 3: server — `default_model_factory` wires the ledger; whole agent turn on the fake
  - [ ] Milestone 4: `load_env()` in `python -m surmap.agent`, `python -m surmap.mapqa`, `scripts/mission_demo.py` and the gated live tests
  - [ ] Milestone 5: live `echo` round trip (`SURMAP_LIVE_FIREWORKS=1` + `FIREWORKS_API_KEY`) — run it, or record why it was not run
  - [ ] Acceptance: `tests/test_agent_llm_fireworks.py`, `tests/test_agent_llm_registry.py`, `tests/test_agent_server_app.py`, `tests/test_mapqa_cli.py` pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (offline suite; the live Fireworks result or why it was not run)
  - [ ] `docs/agent.md` — Models: the `fireworks:` row, its env vars, errors, usage; Running: `--model fireworks:<id>`, keys from `.env`
  - [ ] `docs/credits-usage.md` — add the Fireworks row; keys go in `.env`
  - [ ] `.env.example` — `MODEL_API_KEY`, `FIREWORKS_API_KEY` and the optional model / URL variables; header names every loader
  - [ ] `docs/surmap/changelog/2026-11-03-agent-fireworks-provider.md` — write changelog entry (with the deferred-answer row)
  - [ ] Validate tests (`/validate-tests`)

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-agent-fireworks-provider-initial-discovery.md](./2026-11-03-agent-fireworks-provider-initial-discovery.md).

## Affected Packages

- **surmap** (`src/surmap/agent/llm`, `src/surmap/agent/server/app.py`, `src/surmap/agent/__main__.py`,
  `src/surmap/mapqa/cli.py`), `scripts/mission_demo.py`, `pyproject.toml`, `uv.lock`, `.env.example`.

## Related Feature Documentation

- PRD: [PRD-2026-11-03-agent-fireworks-provider.md](./PRD-2026-11-03-agent-fireworks-provider.md)

## Summary

`fireworks:<model>` ids drive the survey agent on Fireworks' OpenAI-compatible chat completions API
through a thin `langchain-openai` `ChatOpenAI` subclass that adds SurMap's usage ledger, budget gate
and key-safe errors. Provider keys for Fireworks and Muse are read from the project `.env` by every
entry point that needs them.

## Background

Developer request (2026-11-03): "add support for FIREWORKS provider (it might be using OpenAI
interface)". Follow-up requirements from the developer: tests use a fake Fireworks provider on a
real socket, not mocks of the HTTP client; API keys come from the project `.env` for Fireworks and
Muse.

## Scope

- Fireworks chat model, registry listing and building, server wiring, docs, `.env.example`
- `load_env()` in `python -m surmap.agent`, `python -m surmap.mapqa`, `scripts/mission_demo.py`, and
  the gated live tests
- **Out of scope:** Fireworks for labelling or Ask the map; per-model tool-capability filtering of
  the endpoint's listing; image parts to Fireworks vision models (the runtime sends tool images as
  a text placeholder already)

## Technical Changes

### State A (Current)

The registry knows `meta:` and `ollama:`; anything else raises `UnknownModelProvider`.
`default_model_factory` wires the ledger only into `MetaResponsesChatModel`. `load_env()` exists
(`src/surmap/env.py`) but only `scripts/demo.py` calls it; the agent, Ask the map and the mission
demo read `MODEL_API_KEY` from the shell only.

### State B (Target)

```python
# surmap.agent.llm.fireworks
FIREWORKS_PROVIDER = "fireworks"
DEFAULT_FIREWORKS_URL = "https://api.fireworks.ai/inference/v1"
DEFAULT_FIREWORKS_MODELS: tuple[str, ...]          # tool-capable defaults
class FireworksError(RuntimeError): ...
class FireworksChatModel(ChatOpenAI):              # usage_sink, before_call
    # _generate/_agenerate/_stream/_astream: key check → before_call("fireworks") → super()
    #   → usage to usage_sink; openai errors → FireworksError(type name, status), `from None`
def fireworks_base_url(explicit: str | None = None) -> str          # https, or loopback http
def fireworks_chat_model(model, *, api_key, base_url=None, usage_sink=None, before_call=None,
                         max_retries=2) -> FireworksChatModel
class FireworksModelsTransport(Protocol):
    def get_json(self, url: str, headers: Mapping[str, str]) -> Mapping[str, object]: ...
class UrllibFireworksModelsTransport: ...          # 2 s timeout, https or loopback http
def fireworks_models(transport, *, api_key, base_url, override: str | None) -> tuple[str, ...]

# surmap.agent.llm.registry
Provider = Literal["meta", "fireworks", "ollama"]
ChatModelRegistry(*, environ, ollama_transport, meta_transport, fireworks_transport, usage_sink)
```

`available()` lists Muse, then Fireworks (only with `FIREWORKS_API_KEY`), then Ollama.

### Delta (What's Changing)

#### surmap

- `src/surmap/agent/llm/fireworks.py` (new); `registry.py`; `server/app.py`; `agent/__main__.py`
- `src/surmap/mapqa/cli.py` (`load_env()` in `main`); `scripts/mission_demo.py` (`load_env()` in `main`)
- `tests/fake_fireworks.py` (new), `tests/test_agent_llm_fireworks.py` (new),
  `tests/test_agent_llm_registry.py`, `tests/test_agent_server_app.py`, `tests/test_mapqa_cli.py`,
  `tests/test_agent_llm_meta.py` (live test loads `.env`)
- `pyproject.toml`, `uv.lock` — `langchain-openai>=1.1,<2`
- `.env.example`, `docs/agent.md`, `docs/credits-usage.md`

## Verification

**Method:** V1 — fail→pass offline tests against a fake Fireworks provider on a real loopback socket;
plus a live-gated V1 round trip
**Command:** `uv run pytest -q tests/test_agent_llm_fireworks.py tests/test_agent_llm_registry.py tests/test_agent_server_app.py tests/test_mapqa_cli.py`;
live: `SURMAP_LIVE_FIREWORKS=1 uv run pytest -q tests/test_agent_llm_fireworks.py -k live` (key from `.env` or the shell)
**Before:** red — stubs raise `NotImplementedError`, the registry refuses `fireworks:`, entry points ignore `.env`
**After:** green offline; the live result recorded at wrap

**Limit of the fake.** The fake proves that the adapter's real client (`ChatOpenAI` → `openai` →
`httpx`, real bytes over a real socket) agrees with a stub written from Fireworks' documented
OpenAI-compatible wire format. It does not prove agreement with Fireworks itself; that is the gated
live test. A `langchain-openai` / `openai` upgrade that changes the wire format fails an offline
test.

## Testing Plan

- `tests/fake_fireworks.py`: `FakeFireworksScript(rounds, status, served_models)` records every
  request (method, path, case-insensitive headers, parsed JSON body); `serving(script)` runs it on
  `HypercornHost` port 0 in a thread and yields the base URL (`http://127.0.0.1:<port>/v1`).
  `POST /v1/chat/completions` answers a whole `chat.completion` or, when the request streams, SSE
  `chat.completion.chunk` frames ending in `data: [DONE]`; `GET /v1/models` answers
  `{"data": [{"id": …}]}`. Each round is one chat request; the last repeats.
- Construction tests need no socket: built through the registry and inspected.

## Acceptance Tests

### surmap

- `tests/test_agent_llm_fireworks.py`
  - a turn posts to `<base>/chat/completions` with the model id and `Authorization: Bearer <key>`
  - bound tools are sent in OpenAI `tools` shape
  - a `tool_calls` reply becomes `AIMessage.tool_calls`, whole and streamed
  - usage reaches the ledger under `fireworks`, whole and streamed; a spent budget sends nothing
  - a 401 names `FIREWORKS_API_KEY` and a 500 names its status; neither error contains the key
  - a missing key or a cleartext non-loopback URL is refused before any request; `repr` hides the key
  - (live) a Fireworks model calls `echo` and answers with its result
- `tests/test_agent_llm_registry.py`
  - Fireworks listed only with `FIREWORKS_API_KEY`: override list, `GET /models`, built-in fallback
  - Muse, then Fireworks, then Ollama
  - `fireworks:accounts/fireworks/models/x` builds that model on the configured URL with a secret key
- `tests/test_agent_server_app.py`
  - `--model fireworks:<id>` is the config's model
  - the factory gates and records Fireworks calls in the ledger
  - a whole turn on `fireworks:<id>` over the fake calls `list_demos` and finishes `STOP`
  - `main()` reads `.env`: Fireworks and Muse are listed; a shell export wins over the file
- `tests/test_mapqa_cli.py`
  - `ask` with no explicit key uses `MODEL_API_KEY` from `.env`

### Red step (commit 2)

25 tests fail on this PR's own stubs (`NotImplementedError` in `fireworks.py`, the registry's
`UnknownModelProvider` for `fireworks:`, the missing `load_env()` calls); none reaches anything
else. Three new tests already pass and stay as guards: no key → no Fireworks listing, the
`--model fireworks:<id>` config, and the shell beating `.env`. The live Fireworks test is skipped
unless `SURMAP_LIVE_FIREWORKS=1`.

- `tests/test_agent_llm_fireworks.py` — 13 offline + 1 live: request path, model and bearer;
  OpenAI `tools`; `tool_calls` whole and streamed; streamed text; usage whole and streamed;
  budget refusal; 401 / 500 redaction; missing key; cleartext URL; `repr`
- `tests/test_agent_llm_registry.py` — 7 failing + 1 guard: override list, `GET /models`,
  unreachable fallback, order; `build` with slashes, secret key, configured URL
- `tests/test_agent_server_app.py` — 4 failing + 2 guards: `.env` listing, budget, ledger, the
  whole turn on the fake
- `tests/test_mapqa_cli.py` — 1 failing: `ask` keyed from `.env`

Baseline before: 1631 passed, 33 skipped (with this PR's guards); after red: the same plus 25
failing.

## Deferred Answers

| Record | Kind | Question | Pick |
|---|---|---|---|
| [`docs/surmap/deferred-answers/2026-11-03-fireworks-default-models.md`](../deferred-answers/2026-11-03-fireworks-default-models.md) | Product | Which Fireworks models are listed when neither `SURMAP_FIREWORKS_MODELS` nor `GET /models` answers, and where Fireworks sits in the picker | three tool-capable chat models; after Muse, before Ollama |

## Decisions & Trade-offs

- **`ChatOpenAI` subclass, not callbacks** (plan): the budget gate must *refuse* before the request,
  and a LangChain callback's exception is swallowed by default; usage and error translation also
  need the call's result. Overriding `_generate` / `_agenerate` / `_stream` / `_astream` around
  `super()` keeps the stock wire mapping and adds only SurMap's concerns.
- **`stream_usage=True`, `use_responses_api=False`** (plan): the runtime streams, so usage must come
  on the streaming path; Fireworks serves chat completions, never the Responses API.
- **Errors carry only the exception type and status, raised `from None`** (developer requirement):
  the `openai` exception holds the request, which holds the key.
- **Cleartext URLs only on loopback** (plan): `SURMAP_FIREWORKS_URL` must be `https`, or `http` on
  `127.0.0.1` / `localhost` / `::1` (the fake), so the key never crosses a network in clear text.
- **Listing asks `GET /models` when no override is set** (developer requirement), with a 2 s
  timeout and the built-in list on any failure; the endpoint lists every model the account can
  call, not only tool-capable ones, so `SURMAP_FIREWORKS_MODELS` is the way to narrow it.
- **`.env` is loaded in `main()`, never in `config_from_args`** (developer requirement): parsing
  stays pure; the shell wins over the file (`load_env`'s contract).
- **`langchain-openai` added** (developer request names the OpenAI interface; brief plans it).
