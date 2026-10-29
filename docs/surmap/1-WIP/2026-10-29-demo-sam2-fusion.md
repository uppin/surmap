# Changeset: SAM 2.1 + RTAB-Map demo

**Date**: 2026-10-29
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package; an ONNX adapter seam, a demo worker thread, pure fusion math

## Workflow

- [wf 1] ✅ 2026-10-29 `/plan-red` Plan — changeset, initial discovery · this file + companion
  - [x] Record initial discovery (SAM 2.1 export spike, RTAB-Map frame probe)
  - [x] Cross-check src/surmap/docs/todo/: nothing on this path
  - [x] Create changeset (requirements: the SAM PRD in this directory, with SAM 2.1 standing in until SAM 3 access)
  - [x] Build and baseline healthy (468 passed, 5 skipped)
- [wf 2] ✅ 2026-10-29 `/plan-red` Red — acceptance and failing lower-tier tests · collection errors, no `surmap.survey.sam2` / `surmap.demo.fusion`
  - [x] `tests/test_sam2.py`: box-prompted segmenter over a fake session (+ real-model check when exported)
  - [x] `tests/test_demo_fusion.py`: camera→base, mask membership, semantic layer
  - [x] `tests/test_demo_sam2.py`: `segments` events, semantic layer in `final`
- [wf 3] ✅ 2026-10-29 `/green` Green — implement until every red test passes · 26 new tests green; suite 494 passed, 5 skipped
  - [x] `surmap.survey.sam2`: `OnnxSam2Session` (encoder on the Mac GPU via CoreML, decoder on CPU), `Sam2BoxSegmenter`
  - [x] `surmap.demo.fusion`: `camera_to_base`, `points_in_mask`, `SemanticLayer`
  - [x] Demo: live SAM worker (best-effort drop), `segments` events, keyframe fusion after flush, page overlay + map layer
  - [x] `scripts/fetch_sam2_model.py` (tooling-only export) and `scripts/demo.py --sam2-model-dir`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [x] `README.md` § Demo — SAM 2.1 flags and model fetch
  - [ ] `docs/surmap/changelog/2026-10-29-demo-sam2-fusion.md`
  - [ ] Delete this changeset and its companion from `docs/surmap/1-WIP/`
  - [ ] Lint, type-check, and tests green

## Initial Discovery

[initial-discovery.md](./2026-10-29-demo-sam2-fusion-initial-discovery.md)

## Summary

A demo where RTAB-Map and SAM work together:

- Coral boxes are box prompts for SAM 2.1, and each mask inherits its
  Coral label.
- Masks are drawn live on the video, best effort, off the pacing loop.
- After RTAB-Map's map is built, the posed keyframes are segmented.
  Their stereo points inside each mask are placed with RTAB-Map's
  pose, and the map shows them as a labelled object layer over the
  static cloud.

## Technical Changes

### State A (Current)

The demo shows stereo points, Coral boxes and, at the end, the batch
RTAB-Map cloud and trajectory. There is no segmentation. The only SAM
adapter is for an image-only SAM 3 contract with a fake model.

### State B (Target)

- `surmap.survey.sam2`: `Sam2Session` protocol, `OnnxSam2Session`
  (encoder and decoder graphs plus `manifest.json`), and
  `Sam2BoxSegmenter.segment(rgb, prompts) -> tuple[Sam2Segment, …]`.
  Each `Sam2Segment` is a `SamDetection` plus a frame-sized boolean
  mask.
- `surmap.demo.fusion`: `camera_to_base(cam0_yaml)` (`B · T_BS`),
  `points_in_mask` and `SemanticLayer`. Map placement is two
  `to_map_frame` hops.
- The demo emits `segments` events, keyed by `frame_id`. `final` gains
  `semantic` (per label: count and sampled XY) and `sam`
  (analysed, dropped, ms). Without `--sam2-model-dir`, behaviour is
  unchanged.
- Scope guardrail: the semantic layer is separate from the RTAB-Map
  cloud and never fed into RTAB-Map. Only frames with an RTAB-Map pose
  are placed. EuRoC V1_01 is a static room, so there are no moving
  objects to exclude. Motion gating is out of scope here.

## Verification

Smoke run, 2026-10-29 (300 pairs from index 1000, real RTAB-Map
sidecar, real Coral CPU twin, real SAM 2.1 ONNX, CPU): 300 frame
events and 14 live `segments` events (about 1.3 s per SAM frame;
14 analysed, 79 skipped while busy). RTAB-Map returned 15 poses and
a 34,843-point cloud. 4 keyframes had Coral boxes and were segmented,
giving semantic layers `bed` (45 points) and `microwave` (12 points).
Labels are COCO classes from Coral on the Vicon room, so they are not
meaningful scene semantics.

- `uv run pytest -q` and the three other gates.
- Manual: `uv run python scripts/fetch_sam2_model.py`, then
  `uv run python scripts/demo.py --coral-model-dir tests/fixtures/coral_model --sam2-model-dir ~/.cache/surmap/sam2/sam2.1-hiera-small`,
  full sequence. Record the keyframes segmented, labels, point counts
  and SAM ms per frame.
