# Survey agent — Fireworks chat models, and provider keys from `.env`

**Date:** 2026-11-03
**Feature:** Survey agent

The survey agent gained a third model provider. `fireworks:<model>` ids (the model a path such as
`accounts/fireworks/models/llama-v3p3-70b-instruct`; ids split at the first colon) run on Fireworks'
OpenAI-compatible chat completions API through `langchain-openai`'s `ChatOpenAI`, as
`FireworksChatModel`. With `FIREWORKS_API_KEY` set, the model picker lists Fireworks models after
Muse and before the local Ollama ones — from `SURMAP_FIREWORKS_MODELS`, else the endpoint's
`GET /models`, else three built-in tool-capable models. Every call is gated by the usage ledger's
`SURMAP_BUDGET_FIREWORKS_*` budget and recorded under provider `fireworks`, streamed or not.
Failures surface as `FireworksError` with only the exception type and HTTP status — never the key —
and a 401 says to check `FIREWORKS_API_KEY`. `SURMAP_FIREWORKS_URL` must be `https` or loopback
`http`.

Provider keys now come from the project `.env` as well as the shell: `python -m surmap.agent`,
`python -m surmap.mapqa`, `scripts/mission_demo.py` and the Muse / Fireworks live tests call
`load_env()` first, and a shell export still wins. `.env.example` lists `MODEL_API_KEY`,
`FIREWORKS_API_KEY` and the optional model and URL variables. New runtime dependency:
`langchain-openai`.

Tests drive the real client against a fake Fireworks provider on a real loopback socket, including a
whole agent turn that calls `list_demos`; the live `echo` round trip
(`SURMAP_LIVE_FIREWORKS=1`) was not run — no key on the dev host.

Behaviour is described in [docs/agent.md](../../agent.md#models-surmapagentllm).

**Deferred answers** — decided under `#yolo`, awaiting review at wrap:
- `docs/surmap/deferred-answers/2026-11-03-fireworks-default-models.md` — Fireworks models listed when no override or endpoint answers, and picker order → b) three tool-capable models; Muse, Fireworks, Ollama
