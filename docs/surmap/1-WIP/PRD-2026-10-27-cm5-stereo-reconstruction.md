# CM5 stereo reconstruction — PRD

**Date**: 2026-10-27
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Board API (docs/architecture.md §10) — the CM5
  stream gains real scene points from real frames.

## Summary

Give the CM5 a real, CI-runnable scene-point implementation: decode
the streamed stereo frames, reconstruct camera-frame points by block
matching, place them in the map frame with the SLAM pose, and stream
them under designation 1. An end-to-end test drives ten real ETH3D
stereo pairs through the real server and asserts detections are there.

## Proposed Changes

### What's Changing

- `surmap.survey.stereo`: frame decoding (MJPEG / RAW_RGB),
  principal-point alignment, SAD block matching, back-projection —
  numpy + Pillow, pure Python, no native dependency.
- `stream_survey` gains an optional stereo point source; the CM5
  entrypoint uses the real reconstructor by default.
- Fixture: ten ETH3D `cables_2` pairs + scaled calibration under
  `tests/fixtures/eth3d_cables2/`.

### What's Staying the Same

- Pose still comes from `SlamBackend` (RTAB-Map on hardware,
  in-memory in tests); object points still come from their own port.
- No RTAB-Map, camera, or model is needed in CI — ever.

## Acceptance Criteria

- [ ] The fixture e2e streams point batches for the real frames: detections present, sane depths.
- [ ] A frame with no stereo partner or no pose still produces no points.
- [ ] Full CI gates stay green on 3.11/3.12.
