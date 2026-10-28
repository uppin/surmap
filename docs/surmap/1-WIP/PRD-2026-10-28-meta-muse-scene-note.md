# Meta Model API scene note - PRD

**Date**: 2026-10-28
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Hackathon credits ([HACKATHON.md](../../../HACKATHON.md)) — the Meta Model API scene-note cell moves from planned to a client in `src/`
- **Related Feature**: Model policy ([README.md](../../../README.md)) — the hosted Muse Spark scene-note line names the client

## Summary

One civilian search-and-rescue scene note per call, from hosted Muse Spark
(`muse-spark-1.3`) on the Meta Model API. The note describes the mapped area
and does not give flight advice.

## Background

Follow-up task 2 on PR #28. The credits table recorded the scene note as
planned. The owner verified the Responses API request and response shape on
2026-10-28. Muse Wonder is not covered by the credits in use.

## Proposed Changes

### What's Changing

- `MetaMuseSceneClient.note(labels, frame_jpeg)` posts the labels and one JPEG
  and returns the assistant scene note.
- Default model `muse-spark-1.3`, default `reasoning.effort` `low`, key from
  `MODEL_API_KEY`.
- The HACKATHON.md Meta Model API cell records that client. Baseten and Modal
  stay planned.

### What's Staying the Same

- No flight control, navigation, or mission tasking.
- SAM 3.1 on the Meta Model API is still planned. The in-tree SAM path stays
  ONNX.
- Per-object labels stay on Baseten Muse Spark Open, not this client.
- `docs/architecture.md` is unchanged.

## Impact Analysis

### Technical Impact

- New package `surmap.labelling`. Stdlib HTTP only. No new dependency.
- The API key is an environment variable. It is not logged.

### User Impact

- A rescue team can read one scene note for a mapped frame. The model is not
  asked to fly or retask the aircraft.

## Implementation Plan

1. Failing tests for the posted host, model, image part, reasoning effort, and
   note extraction.
2. Client and urllib transport that does not follow redirects.
3. Update the HACKATHON.md scene-note cell and the README line that names it.

## Acceptance Criteria

- [ ] Fake transport sees host `api.meta.ai`, model `muse-spark-1.3`, and the returned note is the assistant `output_text`
- [ ] Live call only when `SURMAP_LIVE_META=1`
- [ ] ruff, mypy strict, and pytest pass
- [ ] HACKATHON.md Meta Model API scene-note cell updated

## References

### Affected Features (Complete List)

- [HACKATHON.md](../../../HACKATHON.md) — credits table
- [README.md](../../../README.md) — model policy scene-note line

### Related Documentation

- PR #28 comment: follow-up task 2
- https://dev.meta.ai/docs/image-understanding — `input_image` / `image_url` string
- https://dev.meta.ai/docs/models — `muse-spark-1.3`
