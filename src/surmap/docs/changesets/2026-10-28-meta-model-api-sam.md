# Meta Model API SAM 3.1

**Date:** 2026-10-28
**Type:** Feature
**Packages:** surmap

Added `surmap.survey.meta_sam.MetaSamDetector`, a `SamDetector`
adapter over `POST https://api.meta.ai/v1/responses`. The default
model id is `sam-3.1` and is configurable. Ids containing
`wonder-full` or `wonder_full` are rejected. Frames go out as base64 data URLs (jpeg for mjpeg,
PNG for raw RGB) with a noun-phrase prompt. Boxes and masks come
back as `SamDetection` values; the polygon reuses `mask_outline`
from `surmap.survey.sam3`. Mask bytes are decoded with
`meta-sam-parser`, not a vendored codec and not model weights.

Each detector counts requests up to `max_calls_per_session`
(default 5000, or `SURMAP_META_SAM_MAX_CALLS`). `before_call("meta")` can refuse a call before it
is counted. `on_usage` receives provider `meta`, the model id, and
input, output, and optional reasoning token counts. A failed send
still counts. The API key is not logged.

The segmentation grammar follows the public SAM docs. The
non-streaming JSON envelope is the text Responses shape and is
isolated in `read_responses_body`; a live `sam-3.1` body was not
captured. See `docs/meta-sam.md`.
