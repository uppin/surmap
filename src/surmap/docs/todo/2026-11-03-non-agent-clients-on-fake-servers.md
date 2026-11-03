# 2026-11-03 — Non-agent model clients on fake provider servers

**Category:** Test debt
**Source:** Muse and Ollama agent providers on fake provider servers (PR #88); `docs/agent.md` Models
**Packages:** surmap
**Consent:** n/a — out of scope by the request ("move ollama and muse to use fake stubs too" covers the agent's providers)
**Status:** Open

## What is left

Test the non-agent model clients against fake provider servers on a real loopback socket, like the
agent's providers (`tests/fake_llm_server.py` + one protocol module per provider), instead of
injected fake transports: `src/surmap/labelling/meta_muse.py`, `src/surmap/labelling/ollama.py`,
`src/surmap/labelling/baseten_muse.py`, `src/surmap/labelling/modal_muse.py` and
`src/surmap/mapqa/client.py`.

## Why it could not be done now

The PR was scoped to the survey agent's chat models; these clients have their own suites and wire
formats (Baseten and Modal endpoints have no fake module yet).

## What was done instead

`tests/fake_meta.py` and `tests/fake_ollama.py` exist and can serve the Meta and Ollama clients
as-is; only the Baseten and Modal formats need new protocol modules.

## When it becomes possible

Now — a Test Rebalance · preserves PR per client family.
