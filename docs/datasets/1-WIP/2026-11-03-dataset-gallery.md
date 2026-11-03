# Changeset: Dataset gallery (KITTI grey + colour, GPS preview, split RTAB-Map/SAM tools)

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — proto/contract change, Python + React, dataset extraction

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — changeset, initial discovery · changeset + discovery
  - [x] Discovery companion written
  - [x] User decisions: chat-app gallery, one KITTI drive grey+colour, split RTAB/SAM tools, GPS map preview
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests · red on missing catalogue/colour/tool APIs
- [wf 3] ✅ 2026-11-03 `/green` Green — implement until every red test passes · 1705 pytest + 99 vitest green
  - [x] Extensible catalogue metadata (provider, licence, modality, GPS)
  - [x] KITTI colour variant + oxts GPS extraction, colour display frames
  - [x] Split proto tools + handlers + workspace runs
  - [x] Chat gallery page (thumbnail, licence, GPS map preview)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [x] Verification executed — result recorded (ruff/mypy/pytest/vitest/typecheck, live /datasets smoke)
  - [x] `docs/agent.md` tool table + gallery docs updated

## Initial Discovery

[2026-11-03-dataset-gallery-initial-discovery.md](2026-11-03-dataset-gallery-initial-discovery.md)

## State A / State B / Delta

State A: three demo scenes, KITTI grey only, no licence/thumbnail/GPS in any
catalogue, combined `run_demo` only, no gallery page.
State B: extensible catalogue with provider/licence/modality/location/GPS;
all 156 public KITTI raw drives in grey and colour (shared download per
drive, both runnable, colour SAM frames; generated registry, SHA learned
on first fetch); KITTI GPS track extracted from `oxts`; agent tools to list/prepare
datasets and run RTAB-Map-only or SAM-only; chat gallery with thumbnail,
licence and GPS map preview per dataset.

## Verification

`uv run pytest -q` (targeted files first), `uv run ruff check src tests`,
`uv run ruff format --check src tests`, `uv run mypy`, and in
`web/agent-chat`: `yarn test`, `yarn typecheck`.
