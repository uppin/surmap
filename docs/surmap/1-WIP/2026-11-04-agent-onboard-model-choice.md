# Changeset: the agent chooses the on-board detector model, or none

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — one new tool, one new optional field on two run tools, one CLI flag pair; no
new dependency

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + companion
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance tests for the choice · 12 + 4 red (missing impl)
  - [x] `tests/test_agent_onboard_models.py` red, CLI tests in `test_agent_server_app.py` red
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · 16 green, full suite green
  - [x] proto: `ListOnboardModels`, `onboard_model` on `RunDemoRequest`, `RunRtabmapRequest`, `RunInfo`
  - [x] `OnboardModels` catalogue + per-run detection source in `DemoWorkspace`
  - [x] `--coral-model-dir` / `--coral-model` on `python -m surmap.agent`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [x] `docs/agent.md` — tool catalogue, run tools and CLI flags updated
  - [ ] changelog entry in `docs/surmap/changelog/`

## Initial Discovery

[2026-11-04-agent-onboard-model-choice-initial-discovery.md](2026-11-04-agent-onboard-model-choice-initial-discovery.md)

## Requirements (PRD, inline — agent-facing only)

- R1. `list_onboard_models` lists every on-board detector profile with its title, note, whether
  this station has its files, and which one is the station default (or that the default is off).
- R2. `run_demo` and `run_rtabmap` take an optional `onboard_model`: a profile name runs that
  model on the input frames; `"none"` runs no on-board detection; absent uses the station default.
- R3. An unknown model is `INVALID_ARGUMENT`; a known model whose files this station lacks is
  `FAILED_PRECONDITION` and starts no run.
- R4. `get_run` (and both run responses) report the on-board model a run used; empty when none.
- R5. Passive survey only: the choice changes what processes recorded frames, nothing else.

## State A

Agent runs never run on-board detection; the host-wide Coral source is fixed at server start and
the agent process cannot configure one.

## State B

`DemoWorkspace` holds an `OnboardModels` catalogue (model dir, station default, a source builder).
Each run resolves its choice, builds a fresh detection source (fresh tracker state) and overrides
the player's `detection_source` for that run only. The run title records ` · On-board: <model>`
ahead of the SAM part, and `RunInfo.onboard_model` reads it back.

## Delta

| Area | Change |
|---|---|
| `proto/surmap/agent/v1/survey_tools.proto` | `ListOnboardModels` rpc; `onboard_model` fields |
| `surmap.agent.tools.onboard` | new: `OnboardModels`, `OnboardModel`, `ONBOARD_OFF` |
| `surmap.agent.tools.port` / `workspace` | `onboard_models()`; `onboard_model=` on the run methods |
| `surmap.agent.tools.handlers` / `dataset_handlers` | the new tool and fields, error mapping |
| `surmap.agent.server.app` / `__main__` | Coral model dir + default in config and CLI |

## Verification

V1 — `uv run pytest -q tests/test_agent_onboard_models.py` plus the full gate set.
