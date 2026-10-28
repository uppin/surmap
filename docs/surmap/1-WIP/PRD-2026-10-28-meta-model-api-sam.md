# Meta Model API SAM 3.1 - PRD

**Date**: 2026-10-28
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Station SAM — `docs/architecture.md` §3.1 and `docs/meta-sam.md`. Hosted segmentation beside the ONNX adapter.

## Summary

Masks from Meta Model API `sam-3.1` returned as `SamDetection`, with a session call cap and usage hooks.

## Background

The hackathon SAM credit is the hosted model, not a weight download. The station port already exists. This PRD adds the HTTP adapter on a branch off main.

## Proposed Changes

### What's Changing

- New `MetaSamDetector` implementing `SamDetector`.
- Request: `POST https://api.meta.ai/v1/responses`, bearer `MODEL_API_KEY`, model id configurable, default `sam-3.1`.
- Response boxes and masks become `SamDetection` polygons.
- Optional `on_usage` and `before_call`. `max_calls_per_session` default 200.
- Live network only when `SURMAP_LIVE_META=1`.

### What's Staying the Same

- `Sam3Detector` and its tests.
- No flight control, navigation, or mission orchestration.
- Object points are not written back into RTAB-Map.

## Impact Analysis

### Technical Impact

- New dependency: `meta-sam-parser` for the documented mask grammar. Not weights.
- Stdlib HTTP. No Modal process.

### User Impact

- A station process can construct `MetaSamDetector` instead of the ONNX detector. The server CLI is unchanged in this change.

## Implementation Plan

1. Failing tests against a fake transport.
2. Adapter, shared outline helper, call cap, hooks.
3. Runbook in `docs/meta-sam.md`. README is not edited.

## Acceptance Criteria

- A fake response with one box and a small mask yields one `SamDetection` with a non-empty polygon.
- No weight download and no Modal process.
- Live call only when `SURMAP_LIVE_META=1`.
- ruff, mypy strict, and pytest pass.
- SAM cell text is recorded for `HACKATHON.md` in `docs/meta-sam.md` because that file is not on main.

## References

### Related Documentation

- https://dev.meta.ai/docs/sam/segmenting
- https://dev.meta.ai/docs/sam/reading-segmentation
- https://dev.meta.ai/docs/protocols/responses
- Follow-up comment on PR 28
