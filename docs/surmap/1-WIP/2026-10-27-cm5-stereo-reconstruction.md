# Changeset: CM5 stereo reconstruction

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — new numeric module + deps, server wiring, real-data e2e

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
  - [x] Record initial discovery (dataset + prototype verified by hand)
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Stub API — `surmap.survey.stereo` signatures (`TODO(cm5-stereo)`)
  - [ ] Create failing acceptance tests (fixture e2e + unit)
  - [ ] Run acceptance tests (verify they fail)
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Add numpy + Pillow deps
  - [ ] Decode + align + block-match + back-project
  - [ ] Wire into `stream_survey` and the CM5 entrypoint default
  - [ ] Acceptance: fixture e2e asserts detections present
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/architecture.md` §10 — real stereo source named

## Initial Discovery

Full exploration that grounded this plan: [initial-discovery.md](./2026-10-27-cm5-stereo-reconstruction-initial-discovery.md).

## Affected Packages

- **surmap**: new `src/surmap/survey/stereo.py`; `cm5_server` wiring; `cm5_main` default
- **repo**: `pyproject.toml`/`uv.lock` (numpy, Pillow); `tests/fixtures/eth3d_cables2/`

## Summary

Adds real stereo scene-point reconstruction to the CM5 stream and a
real-data e2e that proves detections on ETH3D frames, in CI, offline.

## Technical Changes

### State A (Current)

- Streamed frame bytes reach no point-producing code; scene points
  exist only from test fakes.

### State B (Target)

- `surmap.survey.stereo.StereoRig` (intrinsics both cameras + baseline)
  and `StereoReconstructor.reconstruct(left, right, rig)` where frames
  are `(width, height, encoding, data)` decodable to grayscale:
  principal-point alignment, SAD block matching (downscaled),
  back-projection to camera-frame `Vec3`s with depth/validity filters.
- `stream_survey(..., stereo=None)`: when a reconstructor is wired,
  scene points come from the completed pair's frames (camera frame →
  map frame via the SLAM pose); otherwise from `static_points` as
  before. `cm5_main` wires the real reconstructor by default.

## Verification

**Method:** V1 fail→pass — fixture e2e + unit tests
**Command:** `uv run pytest -q tests/test_survey_stereo.py tests/test_survey_cm5_stereo_e2e.py`
**Before:** tests fail (module/stub missing)
**After:** detections asserted on all ten real pairs; full gates green
