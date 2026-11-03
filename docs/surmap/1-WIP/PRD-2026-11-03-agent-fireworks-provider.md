# Survey agent — Fireworks chat models - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: [Survey agent](../../agent.md) — Models, Running the agent
- **Related Feature**: [Credit usage](../../credits-usage.md) — Fireworks calls go to the same usage ledger

## Summary

A third provider for the survey agent: open-weight models hosted by Fireworks, reached through its
OpenAI-compatible chat completions API with function tools. Ids are `fireworks:<model>`.

## Background

Developer request (2026-11-03): "add support for FIREWORKS provider (it might be using OpenAI
interface)". Fireworks does serve the OpenAI chat completions dialect, so the stock
`langchain-openai` client is used rather than a SurMap-owned mapping like Muse's.

## Proposed Changes

### What's Changing

- `fireworks:<model>` ids (split at the first colon; the model is a path such as
  `accounts/fireworks/models/llama-v3p3-70b-instruct`) build a `FireworksChatModel`, a thin
  `ChatOpenAI` subclass pointed at `SURMAP_FIREWORKS_URL` (default
  `https://api.fireworks.ai/inference/v1`) with `FIREWORKS_API_KEY` as the Bearer key.
- Listing: only when `FIREWORKS_API_KEY` is set — the comma-separated `SURMAP_FIREWORKS_MODELS`
  when given, else the endpoint's `GET /models` (2 s timeout), else a built-in default list.
- Every response's token usage is recorded under provider `fireworks`; `SURMAP_BUDGET_FIREWORKS_*`
  refuses a call before it is sent.
- Failures surface as `FireworksError` naming only the exception type and HTTP status; a 401 says
  to check `FIREWORKS_API_KEY`. The key never appears in an error, a log or a `repr`.
- `.env.example`, `docs/agent.md`, `docs/credits-usage.md` document it.

### What's Staying the Same

- Muse and Ollama ids, listing order of Muse first, the web UI, the default model.

## Impact Analysis

### Technical Impact

New runtime dependency `langchain-openai` (pulls `openai`, `tiktoken`).

### User Impact

With `FIREWORKS_API_KEY` set, the chat UI's model picker offers Fireworks models after Muse and
before the local Ollama ones; `--model fireworks:<id>` makes one the default.

## Implementation Plan

See the changeset `2026-11-03-agent-fireworks-provider.md`.

## Acceptance Criteria

1. Fireworks models are listed only when `FIREWORKS_API_KEY` is set, from the override, the
   endpoint, or the built-in list when the endpoint is unreachable.
2. `fireworks:accounts/fireworks/models/x` builds a model for `accounts/fireworks/models/x` on the
   configured URL, holding the key as a secret.
3. A turn sends the model id, the bound tools in OpenAI `tools` shape and `Authorization: Bearer`;
   a `tool_calls` reply becomes `AIMessage.tool_calls`, streamed or not.
4. Usage lands in the ledger under `fireworks`; a spent budget sends nothing.
5. A 401 or 500 becomes a `FireworksError` that does not contain the key.
6. A whole agent turn on a `fireworks:` model calls `list_demos` and finishes with `STOP`.
7. Live (gated): a Fireworks model completes an `echo` tool round trip.
