# Per-object Baseten labels - PRD

**Date**: 2026-10-28
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Hackathon credits ([HACKATHON.md](../../../HACKATHON.md)) — Baseten row moves from planned to a client in tree with a gated live call
- **Related Feature**: Model policy ([README.md](../../../README.md)) — Muse Spark Open bullet names the client and the verified chat-completions call

## Summary

A survey caller can send one JPEG crop, the detector's coarse label,
and a map-frame position to Muse Spark Open on Baseten and receive a
parsed object label. The survey loop does not call this yet.

## Background

PR #28 records three hackathon credits as planned and names Baseten
`meta-models/muse-spark-open-1026` for per-object labels. Follow-up
task 1 on that PR asks for the client. A live check on 28 Oct 2026
showed the chat-completions call returns an OpenAI `chat.completion`,
with the answer in `message.content` and a long trace in
`reasoning_content`. The provider default reasoning effort is `xhigh`.

## Proposed Changes

### What's Changing

- New `LabelClient` port and `ObjectLabel` contract.
- `BasetenMuseLabelClient` calls `https://inference.baseten.co/v1/chat/completions`.
- Default model `meta-models/muse-spark-open-1026`, `reasoning_effort` `low`, image crop as an `image_url` data URL, no JSON mode.
- Label text is parsed from assistant `content`. A `label:` line wins; otherwise the first non-empty line. Confidence is `None` when that text has no number.
- Missing `BASETEN_API_KEY` raises before any socket.
- Prompt frames a civilian disaster-response survey and refuses flight or mission advice.
- `HACKATHON.md` Baseten status becomes "client in tree; live call gated".

### What's Staying the Same

- The geometric pipeline does not call Baseten.
- Meta Model API and Modal stay planned.
- `docs/architecture.md` §3.2 is unchanged in this PR.
- No API key is committed or logged.

## Impact Analysis

### Technical Impact

- New package `surmap.labelling`. Stdlib HTTP only. Tests use an injected transport.
- One skipped live test when `SURMAP_LIVE_BASETEN=1` and the key are set.

### User Impact

- No operator-facing UI. A later station step can call the port.
- No flight or navigation behaviour.

## Implementation Plan

1. Failing tests for the fake transport, the parse rules, the missing key, and the gated live call.
2. Port, in-memory client, and Baseten adapter.
3. Hackathon and README notes updated to match the client.

## Acceptance Criteria

- Fake HTTP transport test asserts model id, host `inference.baseten.co`, an image part, and the parsed label.
- No test touches the network unless `SURMAP_LIVE_BASETEN=1` and the key are set.
- Ruff, mypy strict, and pytest pass.
- `HACKATHON.md` Baseten row says "client in tree; live call gated".

## References

### Affected Features (Complete List)

- [HACKATHON.md](../../../HACKATHON.md) — Baseten credit status
- [README.md](../../../README.md) — Muse Spark Open client note

### Related Documentation

- PR #28 follow-up comment: per-object labels from Baseten
- [docs/architecture.md](../../architecture.md) §3.2 — labelling design, not edited here
