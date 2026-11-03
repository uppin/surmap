# Changeset: Survey agent model providers — Muse (Meta Responses) and Ollama

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — adapter / I/O seam to an external API with unverified tool support, custom `BaseChatModel` under mypy strict, live-gated tests

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (commit 1 `d50a197`)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 39 failing — commit 2
  - [x] Create failing acceptance tests
  - [x] Run acceptance tests (verify they fail)
  - [x] TDD Red — write failing unit/integration tests
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

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **5 of 9** · [#81](https://github.com/uppin/surmap/pull/81)
**Branch**: `pr-5-survey-agent` · **Base**: `pr-4-survey-agent`
**Successor**: `pr-6-survey-agent`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance and unit tests

Why the boundary falls here: a provider is a `BaseChatModel`; the runtime (n4) never names one. The
external API risk (Meta function tools) is isolated in this node so it can halt without blocking the
runtime, tools or UI.

### Owned API surface

- `surmap.agent.llm.meta`: `MetaResponsesChatModel` (`model`, `reasoning_effort`,
  `max_output_tokens`, `base_url`, `api_key`, `transport: MetaMuseTransport`, `usage_sink:
  UsageSink`; `bind_tools`, `_generate`, `_agenerate`), `responses_request(...)`,
  `parse_responses(...)`, `MetaResponsesError`, `ReasoningEffort`, `META_PROVIDER`,
  `DEFAULT_AGENT_META_MODEL`, `AGENT_META_MODEL_ENV`
- `surmap.agent.llm.ollama`: `ollama_chat_model(name, *, base_url)`, `ollama_models(transport, *,
  base_url)`, `ollama_base_url`, `OllamaTagsTransport` (`get_json`) + `UrllibOllamaTagsTransport`
- `surmap.agent.llm.registry`: `ChatModelRegistry(*, environ, ollama_transport, meta_transport,
  usage_sink)` (`available → tuple[ModelInfo, ...]`, `build(id) → BaseChatModel`),
  `ModelInfo(id, provider, model)`, `UnknownModelProvider`
- `tests/agent_llm_fakes.py` (test infrastructure, implemented in the red commit):
  `RecordingMetaTransport`, `FakeOllamaTags`, `a_muse_model`, `a_recorded_reply`, `a_reply`, the
  `echo` tool in three shapes, `round_trip` (live driver)

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
- `tests/fixtures/agent/meta_responses_{text,one_call,two_calls,empty}.json` (hand-built bodies)
- `tests/agent_llm_fakes.py`, `tests/test_agent_llm_meta.py`, `tests/test_agent_llm_registry.py`
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

### Red step (commit 2)

39 tests, all failing with `NotImplementedError` raised by this node's own stubs (`meta.py`
`bind_tools` / `_generate` / `_agenerate` / `responses_request` / `parse_responses`, `ollama.py`,
`registry.py`); no test reaches a predecessor's stub — `tests/agent_llm_fakes.py` imports nothing
from n4. Two live tests are skipped unless their variables are set; neither was run here.

- `tests/test_agent_llm_meta.py` — 25 offline + 1 live
  - request mapping: whole conversation → one body (`:73`), shared `call_id` (`:116`), AI text
    before its calls (`:133`), standard image block → `input_image` (`:150`), OpenAI `image_url`
    part (`:169`), no system → no `instructions` (`:183`), no tools → no `tools` (`:194`)
  - tool binding: `BaseTool` (`:208`) and the runtime's portable dict (`:220`) → Responses
    function tool
  - reply mapping: text (`:235`), one `function_call` → dict args (`:249`), two calls in order
    (`:260`), bad JSON → `invalid_tool_calls` (`:275`), usage → `usage_metadata` (`:291`),
    requested model named (`:307`), no `output` list refused (`:318`)
  - the model over a fake transport: endpoint (`:330`), model/effort/cap (`:341`), key only in the
    bearer header (`:360`), missing key refused before a request (`:372`), tool call reaches the
    caller (`:386`), usage in the ledger (`:397`), empty reply retried once (`:409`), two empty
    replies raise (`:423`), `ainvoke` (`:433`)
  - live (`SURMAP_LIVE_META=1`): Muse calls `echo` and answers with its result (`:451`)
- `tests/test_agent_llm_registry.py` — 14 offline + 1 live
  - `available`: keyed → Muse Wonder (`:48`), unkeyed → no Muse (`:59`), `SURMAP_AGENT_META_MODEL`
    (`:70`), Muse before Ollama models in server order (`:83`), stopped server → none (`:97`),
    `SURMAP_OLLAMA_URL` asked (`:108`)
  - `build`: `ollama:llama3.2:3b` → `ChatOllama` (`:123`), binds `echo` (`:135`), configured server
    (`:146`), `meta:` → Muse (`:158`) through the registry transport and key (`:170`), unknown
    provider refused (`:182`)
  - `ollama_chat_model` loopback default (`:194`), `ollama_models` order (`:205`)
  - live (`SURMAP_LIVE_OLLAMA=1` + `SURMAP_OLLAMA_MODEL`): an Ollama turn calls `echo` (`:223`)

Baseline before: 1422 passed, 7 skipped, 42 inherited known-red (n4); after: the same plus these
39, and 2 more skipped (the live tests).

## Decisions & Trade-offs

- **The `function_call` shape is assumed** (red step): the fixtures follow the OpenAI-style
  Responses API — `output: [{type: "message", content: [{type: "output_text", text}]},
  {type: "function_call", call_id, name, arguments}]`, `usage.output_tokens_details` — and the
  request sends `{type: "function", name, description, parameters, strict: false}`,
  `function_call` and `function_call_output` items. Meta has not confirmed any of it; Milestone 4's
  live check does, and a mismatch means fixing the fixtures to what Meta returns before green.
- **`responses_request` takes Responses-shaped tools** (red step): `bind_tools` does the
  conversion (from `BaseTool` or the runtime's `{"type": "function", "function": {…}}` dict) and
  stores the flat tools, so the pure function needs no LangChain tool types.
- **Tool-call `arguments` are sent as `json.dumps(args)`** (red step) and pinned by the
  whole-conversation test; unparseable reply arguments become `invalid_tool_calls`, not an error.
- **The tag listing has its own GET seam** (red step): `labelling.ollama.OllamaTransport` is
  POST-only and `/api/tags` is a GET, so `OllamaTagsTransport.get_json` sits beside it, reusing
  `OllamaError` and the `SURMAP_OLLAMA_URL` default; an unreachable server lists nothing.
- **The registry takes an injected `environ`** (red step), defaulting to `os.environ`, and hands
  its `MODEL_API_KEY` to the Muse models it builds; `build` does not consult `available`.

- **Custom `BaseChatModel`, not `ChatOpenAI(use_responses_api=True)`**: Meta's Responses dialect is
  not guaranteed to match OpenAI's, and SurMap already owns a typed transport and usage ledger for it.
- **Default effort `medium`** for the agent (labels use `low`, Ask the map `high`): agent turns are
  frequent but need planning.
- **If Meta has no function tools**, the Green row halts ⛔ with the API's response; the developer
  then chooses (a JSON-mode tool emulation in this model, or another Muse route). Recorded here so
  the halt is expected, not a surprise.
