# Changeset: Muse and Ollama providers tested against fake provider servers

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Test Rebalance
**Behaviour**: preserves
**Complexity**: 3 — one package (`tests/` + one registry seam), integration tests over a real loopback socket, adapter / I/O seam

Base: `feat/agent-fireworks-provider` (PR #87). Repoint to `main` once #87 merges.

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-test-rebalance` Measure and plan — test shape, deletions, replacements · baseline 72 collected titles in the four suites, `surmap.agent.llm` 84 % lines (514 stmts, 81 miss; `ollama.py` 55 %); 22 fake-transport cases to replace (Muse 12, registry 8, server app 2), 0 e2e deleted
  - [x] Tier counts measured (step 2)
  - [x] Every e2e case triaged (step 3) — none: the moved cases are in-memory fake-transport tests, not e2e
  - [x] Equivalence traced (step 4) — line coverage baseline recorded below
  - [x] Replacements planned (step 5)
  - [x] Design findings recorded (step 6) — D1: the registry has no Muse base-URL seam
  - [x] Changeset, rows and their TODOs written (step 8)
- [wf 2] ⬜ `/plan-red` Red — replacement tests against the fake servers, committed ·
  - [ ] Shared core `tests/fake_llm_server.py` (thread + `HypercornHost` port 0, rounds, status, recorded requests, case-insensitive headers, closed port); `tests/fake_fireworks.py` rebuilt on it, its tests unchanged and green
  - [ ] `tests/fake_meta.py` — `POST /v1/responses` whole JSON: `message`/`output_text` and `function_call` items, usage incl. reasoning tokens
  - [ ] `tests/fake_ollama.py` — `POST /api/chat` NDJSON streaming and `stream:false` whole replies incl. `tool_calls`; `GET /api/tags`
  - [ ] Replacement tests (V1-characterisation) in `tests/test_agent_llm_meta.py`, `tests/test_agent_llm_registry.py`, `tests/test_agent_server_app.py`, `tests/test_agent_server_e2e.py`
  - [ ] One whole agent turn per provider through `build_agent_description` (Muse, Ollama)
  - [ ] Red only where D1's seam is missing (registry-built Muse on a fake base URL); everything else green when written
- [wf 3] ⬜ `/green-100` Green — replacements pass, equivalence proven, old fake-transport tests deleted ·
  - [ ] D1: `ChatModelRegistry(meta_base_url=…)` hands the base URL to every Muse model it builds (default unchanged)
  - [ ] Every replacement test green
  - [ ] Old fake-transport tests deleted; `RecordingMetaTransport`, `FakeOllamaTags`, `a_muse_model`, `bound_tool_names` removed from `tests/agent_llm_fakes.py` when unused
  - [ ] Equivalence: old → new title mapping one-to-one (table below), and `--cov=surmap.agent.llm` line coverage after ≥ before per module
  - [ ] Out-of-scope TODO recorded: non-agent clients (`labelling/{meta_muse,ollama,baseten_muse,modal_muse}.py`, `mapqa/client.py`) onto fake servers
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (coverage before/after, mapping table)
  - [ ] `docs/agent.md` — Models: a testing note covering all three fake providers and their limit
  - [ ] `docs/surmap/changelog/2026-11-03-agent-fake-llm-providers.md` — write changelog entry (with the deferred-answer row)
  - [ ] Validate tests (`/validate-tests`)
  - [ ] Lint, type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Deferred answers carried into the history entries
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Background

PR #87 tests the Fireworks provider against a fake provider server: a scripted HTTP stub on a real
loopback socket that the adapter's real client talks to, so a client-library upgrade that changes
the wire format fails a test. The Muse (`MetaResponsesChatModel`) and Ollama (`ChatOllama` +
`GET /api/tags`) providers are still tested through injected fake transports
(`tests/agent_llm_fakes.py`: `RecordingMetaTransport`, `FakeOllamaTags`), which bypass the real
HTTP clients (`UrllibMetaMuseTransport`, `UrllibOllamaTagsTransport`, the `ollama` package's
`httpx` client). The developer asked to move both onto fake provider servers too.

## State A (before)

- `tests/fake_fireworks.py` holds the whole server core (thread, event loop, `HypercornHost`,
  recording) plus the OpenAI chat-completions protocol.
- Muse tests post through `RecordingMetaTransport` (no socket); Ollama listing reads
  `FakeOllamaTags`; `ChatOllama` is only checked by attribute (`model`, `base_url`) and by
  inspecting the `bind_tools` binding — its chat request is never sent offline.
- `ChatModelRegistry` cannot point a built Muse model at another base URL; only a transport.

## State B (after)

- `tests/fake_llm_server.py`: the shared core (`serving_routes`, `ScriptedRounds`,
  `RecordedRequest`, `a_closed_port`). One protocol module per provider on it:
  `fake_fireworks.py` (unchanged API), `fake_meta.py`, `fake_ollama.py`.
- Every Muse / Ollama behaviour the old tests asserted is asserted against the real client over
  loopback; the pure `responses_request` / `parse_responses` unit tests stay.
- One whole agent turn per provider (`list_demos`, then answer) through `build_agent_description`.
- `ChatModelRegistry(meta_base_url=…)` — a test seam; production default unchanged.
- The limit, documented: these prove client ↔ stub agreement; the gated live tests remain the
  check against the real providers.

## Verification

- **V1-characterisation** — the replacement tests: green when written (the behaviour exists), and
  they would fail if the adapters' wire behaviour changed.
- **V3** — the equivalence measurement:
  `uv run --with pytest-cov pytest -q --cov=surmap.agent.llm --cov-report=term-missing tests/test_agent_llm_meta.py tests/test_agent_llm_registry.py tests/test_agent_llm_fireworks.py tests/test_agent_server_app.py tests/test_agent_server_e2e.py`

  Before (16c917b): `fireworks.py` 82 % · `meta.py` 91 % · `ollama.py` 55 % · `registry.py` 100 %
  · total 84 % (514 stmts, 81 miss). After: every module ≥ its before figure, plus the old → new
  title mapping in the discovery companion with no old title left unmapped.

## Decisions & Trade-offs

- **D1 — Muse base-URL seam on the registry** as a constructor keyword, not a new environment
  variable: no operator-visible behaviour is added (deferred answer
  `docs/surmap/deferred-answers/2026-11-03-registry-muse-base-url-seam.md`).
- `meta_transport` / `ollama_transport` stay on the registry (production seams; removing them is a
  production change outside this PR's scope).
- The Ollama fake answers a whole NDJSON body in one HTTP response; the client still parses it line
  by line, which is what a chunked stream delivers too.

## Out of scope

Non-agent clients (`src/surmap/labelling/{meta_muse,ollama,baseten_muse,modal_muse}.py`,
`src/surmap/mapqa/client.py`) — recorded as a TODO for later.
