# Changeset: Ask the map

**Date**: 2026-10-28
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package, HTTP and Meta Model API adapter seams, fake-transport integration tests

## Workflow

- [wf 1] ✅ 2026-10-28 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
  - [x] Record initial discovery
  - [x] Cross-check src/surmap/docs/todo/ and src/surmap/docs/code-issues/
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7)
- [wf 2] ✅ 2026-10-28 `/plan-red` Red — acceptance and failing lower-tier tests, committed · collection error, no `surmap.mapqa`
  - [x] Acceptance tests written and failing for the right reason
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Local loader for `surmap.semantic_map_snapshot.v1`
  - [ ] Meta responses client: `muse-wonder-1.0`, reasoning effort high, `max_output_tokens` >= 8192, retry once on empty output, refuse wonder-full
  - [ ] `ask`, `report`, and `ask_voice` (`muse-voice-transcribe-1.0`)
  - [ ] `before_call` / `on_usage`; `UsageLedger` when `surmap.usage` imports
  - [ ] CLI `ask|report|ask-voice` and `POST /ask`
  - [ ] Demo snapshot fixture under `examples/`
  - [ ] Acceptance: `tests/test_mapqa.py` passes
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/mapqa.md` — commands, contract, env vars
  - [ ] `docs/surmap/changelog/2026-10-28-ask-the-map.md` — feature history
  - [ ] `src/surmap/docs/changesets/2026-10-28-ask-the-map.md` — package history
  - [ ] Delete this changeset, the PRD, and the discovery companion from `docs/surmap/1-WIP/`
  - [ ] Test quality and fluent readability validated
  - [ ] Production readiness validated
  - [ ] Clean-code fixes applied
  - [ ] Changes validated against the plan
  - [ ] Lint, type-check, and tests green
  - [ ] Docs wrapped; rows and TODOs carried into the wrap commit and the PR body

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-28-ask-the-map-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: [docs/mapqa.md](../../mapqa.md) — Ask the map: client, CLI, `POST /ask`, demo snapshot
  - [docs/surmap/changelog/2026-10-28-ask-the-map.md](../changelog/2026-10-28-ask-the-map.md) — feature history
  - [src/surmap/docs/changesets/2026-10-28-ask-the-map.md](../../../src/surmap/docs/changesets/2026-10-28-ask-the-map.md) — package history

`README.md`, `HACKATHON.md`, and `docs/architecture.md` are intentionally not edited.

## Related Feature Documentation

- [PRD](./PRD-2026-10-28-ask-the-map.md)

## Summary

Responders ask a semantic-map snapshot a question, by text or by a WAV recording, and receive a JSON answer that cites object ids and lat/lon. A Markdown situation report and `POST /ask` use the same client.

## Background

The snapshot file (`surmap.semantic_map_snapshot.v1`) is specified on PR #35 and is not on `main`. The credit ledger is specified on PR #31 and is not on `main`. Ask the map reads the JSON itself and records usage through hooks, writing a `UsageLedger` only when that module imports. The model is Meta Model API `muse-wonder-1.0`. Muse Wonder Full is refused.

## Scope

- Local snapshot loader and a civilian demo file
- Meta Model API client and map question, report, and voice ask
- CLI and `POST /ask` for the web viewer
- Docs in `docs/mapqa.md` with `uv run python` commands
- Tests, including a live test gated on `SURMAP_LIVE_META=1`

## Technical Changes

### State A (Current)

There is no map question API. A semantic map, when a snapshot file exists, cannot be asked a question. No Meta Model API client lives in this repo.

### State B (Target)

`surmap.mapqa.MapQa.ask` posts to `https://api.meta.ai/v1/responses` and returns `MapAnswer`. `report` returns Markdown. `ask_voice` posts the WAV to `https://api.meta.ai/v1/asr/transcribe` and then asks. `python -m surmap.mapqa serve` exposes `POST /ask`.

### Delta (What's Changing)

#### surmap

- **API**: `MapQa.ask`, `MapQa.report`, `MapQa.ask_voice`, `load_snapshot`, CLI, `POST /ask`
- **Implementation**: urllib transport, strict JSON parse, id check against landmarks and dynamic objects
- **Dependencies**: none added

## Decisions & Trade-offs

- Read snapshot JSON locally instead of depending on unmerged PR #35.
- Hooks always. `UsageLedger` is optional behind `import surmap.usage`.
- Voice uses the ASR transcribe endpoint, which is the Model API surface for `muse-voice-transcribe-1.0`, then the responses endpoint for the question.
- `serve` is a fourth CLI verb so the viewer contract has a process to run. `ask`, `report`, and `ask-voice` stay the question commands.
- CORS `Access-Control-Allow-Origin: *` on `/ask` so a local viewer on another origin can post.

## Verification

V1. `tests/test_mapqa.py` fails collection with `ModuleNotFoundError: No module named 'surmap.mapqa'` before the implementation and passes after it. Live Meta calls stay skipped unless `SURMAP_LIVE_META=1`, and that test prints the JSON answer.
