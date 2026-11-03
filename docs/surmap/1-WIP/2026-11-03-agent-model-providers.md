# Changeset: Survey agent model providers — Muse (Meta Responses) and Ollama

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — adapter / I/O seam to an external API with unverified tool support, custom `BaseChatModel` under mypy strict, live-gated tests

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (commit 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: `MetaResponsesChatModel` request mapping (instructions, text, images, function_call, function_call_output, tools)
  - [ ] Milestone 2: response mapping (text, tool calls, usage, ledger)
  - [ ] Milestone 3: `ollama_chat_model` and `ChatModelRegistry`
  - [ ] Milestone 4: live tool round trip on Muse (`SURMAP_LIVE_META=1`) — if the Responses API rejects function tools, halt this row ⛔ with the response body
  - [ ] Acceptance: `tests/test_agent_llm_meta.py`, `tests/test_agent_llm_registry.py` pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (offline suite, plus the live Muse and Ollama results or why they were not run)
  - [ ] `docs/agent.md` — add "Models" section: ids, env vars, defaults, live checks
  - [ ] `docs/credits-usage.md` — add the agent row (Muse via Responses API, usage ledger)
  - [ ] `docs/surmap/changelog/2026-11-03-agent-model-providers.md` — write changelog entry
  - [ ] Validate tests (`/validate-tests`)

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-agent-model-providers-initial-discovery.md](./2026-11-03-agent-model-providers-initial-discovery.md).

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **5 of 9** · #pending
**Branch**: `pr-5-survey-agent` · **Base**: `pr-4-survey-agent`
**Successor**: `pr-6-survey-agent`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance and unit tests

Why the boundary falls here: a provider is a `BaseChatModel`; the runtime (n4) never names one. The
external API risk (Meta function tools) is isolated in this node so it can halt without blocking the
runtime, tools or UI.

### Owned API surface

- `surmap.agent.llm.meta`: `MetaResponsesChatModel`, `responses_request(...)`, `parse_responses(...)`
- `surmap.agent.llm.ollama`: `ollama_chat_model`, `ollama_models(transport)`
- `surmap.agent.llm.registry`: `ChatModelRegistry`, `ModelInfo`

### Green wave

**Wave:** 1 of 4
**Node:** n5
**Concurrent with:** n1, n2, n3, n4, n6
**Blocks:** n8 (builds the session's model from the registry; `ListModels`)

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9

### Greenable independently?

**yes** — it needs only `langchain-core`, which n4's red commit adds to the lockfile; its tests use
recorded Responses bodies and a fake transport.

### Trunk-merge safety

**When this PR merges alone:** additive; existing Meta and Ollama clients untouched; no network in
the default suite. **Local dev data:** no. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `langchain-core` dependency | n4 | in `pyproject.toml` / `uv.lock` from n4's red commit | uses it; adds only `langchain-ollama` |

**Greenable independently?** yes.

## Inherited Restructure — expect rewrite

n2 moves the demo run engine; this node touches no demo file. No fallout expected.

## Affected Packages

- **surmap** (`src/surmap/agent/llm`), `pyproject.toml`, `uv.lock`.

## Related Feature Documentation

- PRD: [PRD-2026-11-03-agent-model-providers.md](./PRD-2026-11-03-agent-model-providers.md)

## Summary

Muse through a SurMap `BaseChatModel` over the Meta Responses API, Ollama through `ChatOllama`, and a
registry. The Responses mapping is two pure functions (`responses_request`, `parse_responses`) so the
offline tests pin it exactly.

## Background

Developer decision (interview, 2026-11-03): Muse via the Meta Responses API only. The endpoint and
headers are verified (`labelling/meta_muse.py:12-20`), function tools are not.

## Scope

- Meta Responses chat model with tools and images; Ollama model; registry; live checks
- **Out of scope:** streaming token deltas from Meta (one chunk per response for now), Baseten

## Technical Changes

### State A (Current)

`mapqa/client.py MetaClient.complete(instructions, user_text)` and `labelling/meta_muse.py` post
Responses bodies without `tools`; `labelling/ollama.py` posts `/api/chat` without tools. Transports
are typed protocols (`HttpTransport.post`, `MetaMuseTransport.post_json`).

### State B (Target)

```python
class MetaResponsesChatModel(BaseChatModel):
    model: str = "muse-wonder-1.0"
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    max_output_tokens: int = 8192
    def bind_tools(self, tools: Sequence[BaseTool | Mapping[str, object]], **kw) -> Runnable[...]: ...
    def _generate(self, messages, stop=None, run_manager=None, **kw) -> ChatResult: ...
    async def _agenerate(...) -> ChatResult: ...

def responses_request(messages: Sequence[BaseMessage], tools: Sequence[Mapping[str, object]], *, model, effort, max_output_tokens) -> dict[str, object]
def parse_responses(body: Mapping[str, object], *, requested_model: str) -> AIMessage
```

### Delta (What's Changing)

#### surmap

- `src/surmap/agent/llm/{__init__,meta,ollama,registry}.py` (new)
- `tests/fixtures/agent/meta_responses_*.json` (recorded/hand-built bodies)
- `pyproject.toml`, `uv.lock` — `langchain-ollama>=1.1,<2`

## Verification

**Method:** V1 — fail→pass offline tests; plus a live-gated V1 round trip per provider
**Command:** `uv run pytest -q tests/test_agent_llm_meta.py tests/test_agent_llm_registry.py`; live: `SURMAP_LIVE_META=1 uv run pytest -q tests/test_agent_llm_meta.py -k live` and `SURMAP_LIVE_OLLAMA=1 SURMAP_OLLAMA_MODEL=<model> uv run pytest -q tests/test_agent_llm_registry.py -k live`
**Before:** red — stubs raise `NotImplementedError`
**After:** green offline; live results recorded at wrap (or the ⛔ halt if Meta rejects function tools)

## Testing Plan

- Request mapping tested on constructed histories (system, human with image, AI with tool calls,
  tool messages) against expected JSON.
- Response mapping tested on fixture bodies: text only, one and two `function_call` items, empty
  output (retry once like `MetaClient.complete`), usage.
- Registry with a fake Ollama `/api/tags` transport and env toggles.

## Acceptance Tests

### surmap

- `tests/test_agent_llm_meta.py`
  - bound tools become `{type: function, name, description, parameters}` entries
  - an AI tool call and its `ToolMessage` become `function_call` / `function_call_output` items with one `call_id`
  - an image human message becomes an `input_image` data URL part
  - a `function_call` output item parses into `AIMessage.tool_calls` with dict arguments
  - usage maps to `usage_metadata` and is appended to the ledger
  - (live) a Muse turn calls `echo` and answers with its result
- `tests/test_agent_llm_registry.py`
  - lists `meta:` only with `MODEL_API_KEY`, `ollama:` only when `/api/tags` answers
  - `build("ollama:<m>")` returns a tool-bindable `ChatOllama`
  - (live) an Ollama turn calls `echo`

## Decisions & Trade-offs

- **Custom `BaseChatModel`, not `ChatOpenAI(use_responses_api=True)`**: Meta's Responses dialect is
  not guaranteed to match OpenAI's, and SurMap already owns a typed transport and usage ledger for it.
- **Default effort `medium`** for the agent (labels use `low`, Ask the map `high`): agent turns are
  frequent but need planning.
- **If Meta has no function tools**, the Green row halts ⛔ with the API's response; the developer
  then chooses (a JSON-mode tool emulation in this model, or another Muse route). Recorded here so
  the halt is expected, not a surprise.
