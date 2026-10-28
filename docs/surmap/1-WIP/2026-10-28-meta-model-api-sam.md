# Changeset: Meta Model API SAM 3.1

**Date**: 2026-10-28
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package, HTTP adapter seam, unit tests with a fake transport

## Workflow

- [wf 1] ✅ 2026-10-28 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
- [wf 2] ✅ 2026-10-28 `/plan-red` Red — acceptance and failing lower-tier tests · collection error, missing `surmap.survey.meta_sam`
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `MetaSamDetector` posts the documented request and maps one box plus a mask to a `SamDetection` with a polygon
  - [ ] No weight download and no separate GPU service; live call only behind `SURMAP_LIVE_META=1`
  - [ ] `on_usage` and `before_call` hooks; `max_calls_per_session` default 200
  - [ ] Model id configurable, default `sam-3.1`; ids containing `wonder` rejected
  - [ ] `mask_outline` shared with the ONNX adapter
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/meta-sam.md` runbook, including the SAM cell text for `HACKATHON.md`
  - [ ] `docs/architecture.md` §3.1 hosted-path bullet
  - [ ] Changelog and package history entry
  - [ ] Test quality and fluent readability validated
  - [ ] Production readiness validated — HTTP adapter and credit cap
  - [ ] Lint, type-check, and tests green

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-28-meta-model-api-sam-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- surmap — new `survey/meta_sam.py` adapter and tests

## Summary

Hosted SAM 3.1 behind `SamDetector`, using the Meta Model API, with a
session call cap and usage hooks. The ONNX path stays.

## Background

Follow-up task 3 on PR 28. The station already has a SAM port and an
ONNX adapter. This change adds the credit-backed HTTP adapter without
downloading weights. `src/surmap/usage.py` is not on main; the hooks
are optional callables so that module can attach later.

## Scope

- `MetaSamDetector` implements `SamDetector`.
- Fake-transport tests, plus urllib tests against localhost.
- `docs/meta-sam.md` holds the runbook. README is not edited.
  `HACKATHON.md` is not on main, so the SAM cell text lives in that note.

## Technical Changes

### State A (Current)

`SamDetector` is implemented by `Sam3Detector` (ONNX) and
`InMemorySamDetector`. `_mask_outline` is private. No code calls
`api.meta.ai`.

### State B (Target)

`MetaSamDetector` calls `POST /v1/responses` with model `sam-3.1`
(configurable), maps the documented segmentation grammar to
`SamDetection`, and shares `mask_outline`. A per-instance cap
defaults to 200 calls. `before_call("meta")` can block a call.
`on_usage` reports token counts. The JSON envelope parser is one
function and documents what was not verified live.

### Delta (What's Changing)

New module, new dependency `meta-sam-parser` (protocol parser, not
weights), public `mask_outline`, tests, `docs/meta-sam.md`, a short
architecture bullet.

## Verification

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest -q
```

Before: the meta SAM tests cannot be collected (`meta_sam` missing).
After: those tests pass, `tests/test_sam3.py` stays green, and the
four commands above are green.

## Decisions & Trade-offs

- Decode masks with `meta-sam-parser` instead of reimplementing the
  base85 arithmetic codec.
- Do not edit README. Do not add `HACKATHON.md` (owned by PR 28, not
  on main). Put the SAM cell text in `docs/meta-sam.md`.
- Stdlib urllib, not a new HTTP dependency.
- Half-open boxes, matching the official parser and `Sam3Detector`.
- Missing confidence scores as `1.0` so an omitted `c` is not a drop.
