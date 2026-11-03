# 2026-11-03 — Fireworks default models and picker order

**Kind:** Product
**Source:** `docs/surmap/1-WIP/2026-11-03-agent-fireworks-provider.md` (PR pending)
**Asked by:** `/plan-red` row 1, under `/yolo`
**Status:** Awaiting review
**Decision:** b) three tool-capable chat models; Fireworks after Muse, before Ollama

## Question

With `FIREWORKS_API_KEY` set but no `SURMAP_FIREWORKS_MODELS` and no answer from Fireworks'
`GET /models`, which models should the chat UI's picker offer, and where do Fireworks models sit
relative to Muse and the local Ollama models?

## Options as asked

| | Option | Consequence |
|---|---|---|
| a) | List nothing | The picker shows no Fireworks model until the endpoint answers or the variable is set |
| b) **(recommended)** | `accounts/fireworks/models/llama-v3p3-70b-instruct`, `accounts/fireworks/models/qwen3-235b-a22b`, `accounts/fireworks/models/kimi-k2-instruct`; order Muse, Fireworks, Ollama | A keyed user always sees usable tool-calling models; hosted models stay together ahead of local ones |
| c) | One model only (`llama-v3p3-70b-instruct`) | Smallest list; less choice |

**Asker's pick:** b) — the three are Fireworks-hosted chat models documented for function calling,
and a keyed user should never face an empty provider.

## What was built on it

`DEFAULT_FIREWORKS_MODELS` and the listing order in `src/surmap/agent/llm/fireworks.py` and
`src/surmap/agent/llm/registry.py`; the registry tests that pin the fallback and the order.

## To override

Edit `DEFAULT_FIREWORKS_MODELS` (a tuple) and the matching registry test; reordering the picker is
one block move in `ChatModelRegistry.available` plus the order test.
