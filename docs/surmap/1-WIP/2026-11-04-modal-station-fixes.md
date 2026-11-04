# Changeset: Modal station fixes — prompt reaches the container, GPU fallback, sam3 numpy

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Bug Fix
**Behaviour**: changes
**Complexity**: 2 — one package (`surmap.survey` + one script), a handful of symbols, unit and AST tests

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — reproduction tests, committed · 7 new tests red (ImportError / AttributeError on the missing fix)
  - [x] Label round trip: the label set at deploy time is the label the container's command runs
  - [x] App wiring (AST): `serve` gets the label through a deploy-time secret, `gpu` from the settings
  - [x] GPU fallback: default `L4` then `A10G`; `SURMAP_MODAL_GPU` takes a comma list
  - [x] sam3 install: its declared runtime deps minus numpy; `sam3` itself installed `--no-deps`, after the pyproject
  - [x] `verify_station.py --prompt` sends the prompt as `concept_prompts`
- [wf 3] ✅ 2026-11-04 `/green` Green — fix until every reproduction passes · 24/24 in both suites; full gates green (2102 passed, 18 skipped)
  - [x] `modal_hosting.StationSettings` (`from_env`, `container_env`) and `SAM3_*` constants
  - [x] `modal_station_app.py` uses them; header docstring updated
  - [x] `verify_station.py --prompt` (default `mattress`, matching the EuRoC fixture)
- [wf 4] ⏳ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (V1 suite; V4 live run on Modal)
  - [ ] `docs/modal.md` §5 — GPU fallback, prompt, `--prompt`, verified-on line for the station
  - [ ] Changelog entry `docs/surmap/changelog/2026-11-04-modal-station-fixes.md`
  - [x] Lint and quality gates green (`ruff format --check`, `ruff check --no-cache`, `mypy`, `pytest`)

## Initial Discovery

Full codebase exploration that grounded this plan:
[initial-discovery.md](./2026-11-04-modal-station-fixes-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- `surmap` — `src/surmap/survey/modal_hosting.py`, `src/surmap/survey/modal_station_app.py`,
  `scripts/verify_station.py`, `docs/modal.md`.

## Summary

The station app deployed on Modal always prompts SAM with `object`, asks for only an L4, and
installs `sam3` with a numpy pin surmap overrides. This fixes all three and lets the station
verifier pass a prompt.

## Background

The first live run of `surmap-station` (2026-11-04, workspace `ginas-bb`) proved the Connect
RPC path and SAM 3.1 on the GPU, and found these defects on the way.

## Scope

In: the three defects above, `verify_station.py --prompt`, the station rows of `docs/modal.md`.
Out: the `surmap-sam` app (`modal_sam_app.py`), which has its own GPU setting; the agent-side
station lifecycle (the follow-up PR).

## Technical Changes

### State A (Current)

- `_LABEL = os.environ.get("SURMAP_STATION_LABEL", "object")` at import — `object` in the container.
- `gpu=os.environ.get("SURMAP_MODAL_GPU", "L4")` — one type, no fallback.
- Image: sam3 with its deps (`numpy<2`) then the pyproject (`numpy>=2.4.6`) → pip conflict warning.
- `verify_station.py` sends no `concept_prompts`.

### State B (Target)

- `modal_hosting.StationSettings` — `gpus`, `label`, `timeout_s`, `scaledown_s`, read by
  `StationSettings.from_env(environ)`; `container_env()` is the env the container needs to read
  the same settings back. The app passes it as `modal.Secret.from_dict(settings.container_env())`,
  so the label set at deploy time is the one `serve()` runs.
- `gpu=settings.gpus`, default `["L4", "A10G"]`; `SURMAP_MODAL_GPU=A10G` or `L4,A100` overrides.
- Image: sam3's declared runtime deps (`SAM3_RUNTIME_PACKAGES`, no numpy) before the pyproject;
  `sam3` itself (`SAM3_PACKAGE`) installed `--no-deps` after it, so numpy is surmap's pin and pip
  has no conflict to report.
- `verify_station.py --prompt <concept>` (default `mattress`) sets `concept_prompts`.

### Delta (What's Changing)

#### surmap

- `modal_hosting.py`: + `StationSettings`, `DEFAULT_STATION_GPUS`, `SAM3_PACKAGE`,
  `SAM3_RUNTIME_PACKAGES`, env-name constants.
- `modal_station_app.py`: module settings from `StationSettings.from_env(os.environ)`; secret;
  image chain reordered.
- `scripts/verify_station.py`: `--prompt`, `verify(..., prompt=...)`.

## Verification

**Method:** V1-fail→pass — reproduction tests for each defect; V4 — one live run on Modal.
**Command:** `uv run pytest -q tests/test_modal_survey_apps.py tests/test_verify_station.py`
**Before:** the new tests fail (missing `StationSettings`, app wiring, `--prompt`).
**After:** all pass.

V4 (the image and the GPU are only reachable on Modal): 1. `modal serve` the station with
`SURMAP_STATION_LABEL=mattress` on `ginas-bb`; 2. confirm the image build log has no
`dependency conflicts` line; 3. `verify_station.py wss://<url> --expect-device gpu --prompt ""`
(no client prompt, so the server's label must do the work) passes with detections; 4. stop the
app. Evidence: the verifier output and the build-log grep, recorded here.
**Approved:** pending — asked before the run.

## Decisions & Trade-offs

- sam3 runs on numpy 2.4.6 (verified on GPU), so surmap's pin wins and sam3 goes in `--no-deps`
  with its other declared deps listed, rather than downgrading numpy for the whole image.
- The label travels in a `Secret.from_dict`, not `Image.env`: an env layer would sit before the
  torch install and rebuild it on every label change.

## Validation Results

(filled by the Wrap row)
