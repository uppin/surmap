# Changeset: Baseten Muse Spark Open labels

**Date**: 2026-10-28
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package, HTTP adapter seam, in-memory transport tests

## Workflow

- [wf 1] ✅ 2026-10-28 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
- [wf 2] ✅ 2026-10-28 `/plan-red` Red — acceptance and failing lower-tier tests, committed · collection errors: `surmap.labelling` and `surmap.usage` missing
  - [x] Fake-transport acceptance test fails because the client is missing
  - [x] Ledger tests fail because `surmap.usage` is missing
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `BasetenMuseLabelClient` parses content, ignores reasoning for the label, caps tokens
  - [ ] `UsageLedger` appends JSONL, totals per provider, `check` raises `BudgetExceeded`
  - [ ] Client calls `ledger.check("baseten")` before the transport and records usage after
  - [ ] `scripts/usage_report.py` prints provider/model/day totals
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/architecture.md` §3.2 names the Baseten model
  - [ ] `HACKATHON.md` Baseten row and credit-usage subsection
  - [ ] Changelog and package history written; `1-WIP/` removed
  - [ ] README.md not modified

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-28-baseten-muse-labels-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## State A

No module calls Baseten, Meta Model API, or Modal. Labelling is an open
model choice in `docs/architecture.md` §3.2. There is no usage log and
no `HACKATHON.md` on `main`.

## State B

`BasetenMuseLabelClient` labels one JPEG crop via
`https://inference.baseten.co/v1/chat/completions`, model
`meta-models/muse-spark-open-1026`, with `reasoning_effort=low` and
`max_tokens` default 1024. `ObjectLabel.raw_text` is the assistant
`content` only. `UsageLedger` is the shared credit callback: one JSON
line per call, process totals, and optional per-provider budgets from
the environment. The report script prints totals by provider, model,
and UTC day. Live HTTP stays behind `SURMAP_LIVE_BASETEN=1`.

## Delta

- Add `src/surmap/labelling/baseten_muse.py` and `src/surmap/usage.py`.
- Add `scripts/usage_report.py`, labelling tests, and ledger tests.
- Add `HACKATHON.md` and point §3.2 at the client. Do not edit README.

## Verification

- `uv run ruff check src tests`
- `uv run ruff format --check src tests`
- `uv run mypy`
- `uv run pytest -q`
- `git diff --name-only origin/main...HEAD` does not include `README.md`
- `git diff --name-only origin/main...HEAD | grep '1-WIP/'` is empty after wrap
