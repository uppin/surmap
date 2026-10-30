# Changeset: one-command disaster mission demo

**Date**: 2026-10-29
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — crosses simulation, survey, labelling, map, and viewer; adapter seams; no new contract on the wire

## Workflow

- [wf 1] ✅ 2026-10-29 `/plan-red` Plan — changeset and initial discovery · this file
- [wf 2] ✅ 2026-10-29 `/plan-red` Red — failing metrics and orchestration tests · `tests/test_mission_metrics.py`, `tests/test_mission_demo.py` failed on missing `surmap.mission`
- [wf 3] ✅ 2026-10-29 `/green` Green — offline chain, live flag gates, viewer impact ·
  - [x] Score detections against `load_disaster_ground_truth().people`
  - [x] Offline command exports the tiny SITL fixture, projects fixture masks, writes the snapshot and `impact.json`
  - [x] "Where are the survivors?" highlights survivor landmarks
  - [x] Live providers stay behind `SURMAP_LIVE_META` / `SURMAP_LIVE_BASETEN` / `SURMAP_LIVE_MODAL`
  - [x] Viewer `GET /impact` and the page banner
  - [x] PR #38's `StreamingRtabmapBackend` is the live map; `surmap.mapqa` stays a named hook
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] Live capture on a WSL host with Gazebo
  - [ ] `docs/mission-demo.md` and the Gazebo overview folded as the stable runbooks (already drafted)
  - [ ] Delete this changeset and the discovery companion

## Initial Discovery

See `2026-10-29-mission-demo-initial-discovery.md`.

### State A

The pieces live on separate pull requests. No command runs them together.

### State B

One offline command writes a fixture-labelled impact report and opens
the viewer. Live mode calls only the flagged clients and reads the
cloud from `StreamingRtabmapBackend`. The survivor total is the
ground-truth `people` array.

### Delta

Mission package, viewer impact route, plural label match for
"survivors", docs, and the merge of #18, #29, #31, #32, #33, #34, #35,
and #37.

## Verification

Offline tests in `tests/test_mission_metrics.py` and
`tests/test_mission_demo.py`. Gates: ruff, mypy, pytest. A live
Gazebo flight is not run in CI.
