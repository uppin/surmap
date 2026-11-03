# Survey agent — Muse and Ollama providers tested against fake provider servers

**Date:** 2026-11-03
**Feature:** Survey agent

The survey agent's Muse (`MetaResponsesChatModel`, Meta Responses API) and Ollama (`ChatOllama` and
the `GET /api/tags` listing) providers are now tested the way the Fireworks provider is: against
fake provider servers — scripted HTTP stubs on a real loopback socket that the adapters' real
clients talk to. The injected fake transports (`RecordingMetaTransport`, `FakeOllamaTags`) are
gone. The server core moved out of `tests/fake_fireworks.py` into a shared
`tests/fake_llm_server.py`, with one protocol module per provider (`fake_fireworks.py`,
`fake_meta.py`, `fake_ollama.py`). Every behaviour the old tests asserted is still asserted, now over
the wire, plus a whole agent turn per provider; `surmap.agent.llm` line coverage rose from 84 % to
89 % (`ollama.py` 55 % → 90 %). The fakes prove client ↔ stub agreement only; the gated live tests
remain the check against the real providers.

No production behaviour changed. `ChatModelRegistry` gained a `meta_base_url` keyword (default the
Meta Model API) so registry-built Muse models can reach the fake.

Testing is described in [docs/agent.md](../../agent.md#tests-fake-provider-servers).

**Follow-up:** `src/surmap/docs/todo/2026-11-03-non-agent-clients-on-fake-servers.md` — the
labelling and map-QA clients onto the same fakes.

**Deferred answers** — decided under `#yolo`, awaiting review at wrap:
- `docs/surmap/deferred-answers/2026-11-03-registry-muse-base-url-seam.md` — how the registry learns a Muse base URL → a) a `meta_base_url` keyword, no new environment variable
