# Baseten Muse Spark Open labels

**Date:** 2026-10-28
**Feature:** Per-object labels from Baseten

Added `surmap.labelling`: a `LabelClient` port, an in-memory client,
and `BasetenMuseLabelClient`. The Baseten client posts one JPEG crop
to `https://inference.baseten.co/v1/chat/completions` with model
`meta-models/muse-spark-open-1026`, sends `reasoning_effort: low`,
and reads the label from `choices[0].message.content`. It does not
parse `reasoning_content` and does not request JSON mode. A missing
`BASETEN_API_KEY` raises `BasetenApiKeyMissing` before any socket.
The prompt frames a civilian disaster-response survey. The survey
loop does not call the client. Live tests run only when
`SURMAP_LIVE_BASETEN=1` and `BASETEN_API_KEY` are both set.

`HACKATHON.md` records the Baseten credit as "client in tree; live
call gated". `docs/architecture.md` §3.2 was left unchanged because
open PR #18 already edits that section.
