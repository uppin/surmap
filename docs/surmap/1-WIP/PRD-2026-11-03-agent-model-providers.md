# Survey agent — Muse and Ollama chat models - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Survey agent (new, `docs/agent.md` created at wrap) — which models drive it
- **Related Feature**: [Credit usage](../../credits-usage.md) — agent calls are recorded in the same usage ledger

## Summary

Two LangChain chat models the agent can bind tools to: Muse on the Meta Responses API (a SurMap
`BaseChatModel`, since no stock integration speaks that API) and a local Ollama model
(`langchain-ollama`). A small registry lists what is available and builds one by name.

## Background

The developer chose the Meta Responses API as the only Muse route for the agent. SurMap calls it
today for single, tool-less requests (`mapqa/client.py`, `labelling/meta_muse.py`). Function tools on
that endpoint are unverified, so the first live check decides whether Muse can drive the agent.

## Proposed Changes

### What's Changing

- `MetaResponsesChatModel(BaseChatModel)`:
  - request: `model` (default `muse-wonder-1.0`, `SURMAP_AGENT_META_MODEL`), `instructions` from the
    system message, `input` items from the history — user/assistant text, `input_image` data URLs,
    `function_call` items for assistant tool calls and `function_call_output` items for tool
    results; `tools: [{type: "function", name, description, parameters, strict: false}]` from
    `bind_tools`; `reasoning.effort` (default `medium`), `max_output_tokens` (default 8192)
  - response: `output_text` → `AIMessage.content`; `function_call` items → `AIMessage.tool_calls`
    (`call_id`, `name`, parsed `arguments`); usage → `usage_metadata` and the SurMap usage ledger
  - transport: the existing typed `post_json` protocol (fakeable); key from `MODEL_API_KEY`
  - streaming: one chunk per response (the endpoint's SSE streaming is a later change)
- `ollama_chat_model(name)` → `ChatOllama(model=name, base_url=SURMAP_OLLAMA_URL)` with tool binding.
- `ChatModelRegistry`: `available()` lists `meta:<model>` (when `MODEL_API_KEY` is set) and
  `ollama:<model>` (from `GET /api/tags` on the loopback server); `build(id)` returns the model.
- Live checks gated by `SURMAP_LIVE_META=1` / `SURMAP_LIVE_OLLAMA=1`: one tool-call round trip each.

### What's Staying the Same

- Existing Muse and Ollama clients (labels, scene notes, Ask the map).

## Impact Analysis

### Technical Impact

New dependency `langchain-ollama`; `langchain-core` arrives with n4.

### User Impact

The chat UI's model picker (n9) lists these ids.

## Implementation Plan

See the changeset `2026-11-03-agent-model-providers.md`.

## Acceptance Criteria

1. A bound tool is sent as a Responses `function` tool with the contract's JSON schema.
2. A recorded `function_call` output item becomes an `AIMessage` tool call with parsed arguments.
3. A `ToolMessage` in history becomes a `function_call_output` item with the matching `call_id`.
4. Usage reaches `usage_metadata` and the ledger.
5. The registry lists only providers that are configured and reachable.
6. Live (gated): Muse and Ollama each complete one tool round trip against a trivial `echo` tool.

## References

### Affected Features (Complete List)

- Survey agent (new); Credit usage (`docs/credits-usage.md`)
