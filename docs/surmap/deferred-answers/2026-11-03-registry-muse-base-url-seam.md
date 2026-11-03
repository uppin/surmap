# 2026-11-03 — Registry seam for the Muse base URL

**Kind:** Technical
**Source:** PR #88 (Muse and Ollama on fake provider servers; changeset wrapped into `docs/surmap/changelog/2026-11-03-agent-fake-llm-providers.md`)
**Asked by:** `/plan-test-rebalance` row 1, under `/yolo`
**Status:** Awaiting review
**Decision:** a) a `meta_base_url` keyword on `ChatModelRegistry`

## Question

Registry-built Muse models always post to `https://api.meta.ai/v1`. To drive them against the fake
Meta server, how should the registry learn another base URL?

## Options as asked

| | Option | Consequence |
|---|---|---|
| a) **(recommended)** | `ChatModelRegistry(meta_base_url=…)`, default `None` (the Meta URL) | Test seam only; no operator-visible behaviour added |
| b) | A new `SURMAP_META_URL` environment variable, like `SURMAP_FIREWORKS_URL` | Operators could point Muse elsewhere — new behaviour in a behaviour-preserving PR |
| c) | Keep injecting `meta_transport` in registry tests | The real client is not exercised through the registry |

**Asker's pick:** a) — the PR preserves behaviour; an environment variable is a feature of its own.

## What was built on it

`src/surmap/agent/llm/registry.py` (`meta_base_url`), the registry / server-app / e2e Muse tests.

## To override

For b), read the variable in `ChatModelRegistry.build` (validating `https` / loopback `http` as
Fireworks does) and drop the keyword; the tests then set it in `environ`.
