# Meta Model API SAM 3.1

**Date:** 2026-10-28
**Feature:** Survey data APIs

Added `surmap.survey.meta_sam.MetaSamDetector`, a `SamDetector` that
posts a frame and a noun-phrase prompt to the Meta Model API
(`sam-3.1` by default, id configurable) and maps the returned boxes
and masks to `SamDetection`. No checkpoint is downloaded. The ONNX
adapter is unchanged. A detector instance stops at
`max_calls_per_session` (default 200). Optional `before_call` and
`on_usage` hooks cover the provider name `meta`. Live tests stay
behind `SURMAP_LIVE_META=1`. The runbook is `docs/meta-sam.md`.
