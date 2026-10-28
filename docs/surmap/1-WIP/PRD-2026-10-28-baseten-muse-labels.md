# Baseten Muse Spark Open labels — PRD

**Date**: 2026-10-28
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Semantic labelling (`docs/architecture.md` §3.2) —
  per-object labels gain an in-tree Baseten client. The station server
  still does not call it.
- **Related**: Hackathon credits (`HACKATHON.md`, created here because it
  is not on `main`) — Baseten status and the credit ledger runbook.
  README is unchanged.

## Summary

A `LabelClient` asks Baseten Muse Spark Open to label one JPEG crop.
A process-wide usage ledger records token spend and can refuse another
call before it is sent when a per-provider budget is set.

## Background

Follow-up on PR #28, comment 6479193887. The owner verified
`POST https://inference.baseten.co/v1/chat/completions` with
`meta-models/muse-spark-open-1026` on 2026-10-28. A trivial prompt spent
about 2200 reasoning tokens, so the client defaults reasoning to `low`
and sends a `max_tokens` cap. Parallel agents need one ledger callback.

## Proposed Changes

### What's Changing

- New `surmap.labelling.BasetenMuseLabelClient` and `ObjectLabel`.
- New `surmap.usage.UsageLedger` plus `scripts/usage_report.py`.
- The client checks `ledger.check("baseten")` before each request and
  records a `UsageRecord` after a response.
- `HACKATHON.md` states the Baseten row as "client in tree; live call
  gated" and documents credit limits. Architecture §3.2 names the model.
  README is not edited.

### What's Staying the Same

- No flight control, navigation, or mission orchestration.
- Object points are not written back into RTAB-Map.
- The station and CM5 servers do not gain a live labelling call.
- Meta Model API and Modal stay uncalled.

## Impact Analysis

### Technical Impact

- Stdlib HTTP only. Tests use an injected transport.
- The ledger file defaults to `~/.surmap/usage.jsonl`.
- Budgets are optional env vars. Unset means no limit.

## Acceptance

- A fake transport test sees model id `meta-models/muse-spark-open-1026`,
  host `inference.baseten.co`, an image part, and the parsed label.
- No test opens a socket unless `SURMAP_LIVE_BASETEN=1` and the key are set.
- Ledger tests cover the JSONL line, per-provider totals, and
  `BudgetExceeded` before the transport runs.
- `uv run ruff check src tests`, `ruff format --check`, `mypy`, and
  `pytest -q` pass.
