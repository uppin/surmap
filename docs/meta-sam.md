# Meta Model API SAM 3.1

Hosted segmentation behind the `SamDetector` port. The ONNX adapter
in `surmap.survey.sam3` is a separate path and is unchanged.

## Run

```python
from surmap.survey.meta_sam import MetaSamDetector

detector = MetaSamDetector(prompt="roof")  # reads MODEL_API_KEY
detections = await detector.detect(frame)
```

- Endpoint: `POST https://api.meta.ai/v1/responses` (override with
  `endpoint=`).
- Auth: `Authorization: Bearer <MODEL_API_KEY>`. The key is read from
  the constructor or from the environment at call time. It is not
  logged. An error string that contains the key is redacted.
- Model id: `sam-3.1` by default (`model=`). Any id containing
  `wonder` is rejected.
- Prompt: a short noun phrase (`prompt=`, default `object`). One
  concept per request, matching the SAM docs.
- Image: an mjpeg frame is sent as its jpeg bytes. A raw RGB frame
  is encoded as PNG. Both go out as a base64 data URL on
  `input_image`.
- `stream` is false.
- Metadata (string values, as the docs require):
  `include_confidence=true`, `mask_encoding=one_bit`.
- Each detector instance allows `max_calls_per_session` requests
  (default 200). The next call raises `MetaSamCallLimit` and does
  not touch the network. A send that fails still counts. A
  `before_call` that raises does not.
- `before_call("meta")` runs after the cap and the key check, before
  the request is counted.
- `on_usage("meta", model, input_tokens, output_tokens, reasoning)`
  runs after a response body is read. `reasoning` is `None` when the
  body has no `output_tokens_details.reasoning_tokens`.

A live call from the test suite happens only when `SURMAP_LIVE_META=1`.
Ordinary tests use a fake transport. Nothing in this path downloads
weights.

Mask rasters are decoded by `meta-sam-parser` (Meta's documented
parser, not model weights).

## What the wire mapping does

`sam_responses_payload` builds the request.
`read_responses_body` reads the JSON envelope.
`detections_from_output_text` maps the segmentation grammar to
`SamDetection`.

Boxes on the wire are inclusive. `box_xyxy` is the half-open box the
parser emits (inclusive max plus one), the same convention as
`Sam3Detector`. The mask raster sits on that box. `mask_polygon` is
`mask_outline` of the raster, shifted onto the box. `label` is the
prompt. `score` is the `c` field, or `1.0` when `c` is absent.
`track_id` is the wire object id.

## Assumed

Checked on 2026-10-28 against the SAM pages and the Responses page
on dev.meta.ai, and against a verified text Responses call
(`output[]`, `usage.input_tokens`, `usage.output_tokens`). A live
`sam-3.1` response was not captured. These parts are therefore
assumptions, isolated in `read_responses_body`:

- A non-streaming SAM response uses that same JSON envelope: the
  grammar arrives as `output[].content[]` blocks with
  `type: output_text`.
- Reasoning tokens, when present, are
  `usage.output_tokens_details.reasoning_tokens`. Text usage that
  was verified had no reasoning field, so a missing field is
  `None`, not zero.
- The request includes `type: message` on the input item, as the
  SAM segmenting examples do. The verified text-call body omitted
  that field.

The grammar itself (frame marker, inclusive box, base85 mask) is
the documented one. The request's model id, URL, bearer auth, and
`input_text` / `input_image` parts are the documented ones.

## SAM cell for HACKATHON.md

`HACKATHON.md` is not on `main`. When that table exists, the SAM
row should say:

- Credits status: hosted SAM is `surmap.survey.meta_sam`, model id
  `sam-3.1` (configurable), `POST /v1/responses`. Live tests only
  with `SURMAP_LIVE_META=1`.
- Third-party use: `MetaSamDetector` posts frames to the Model API.
  `surmap.survey.sam3` remains the ONNX path. No checkpoint is
  downloaded.
- What this repo adds: the `SamDetector` mapping to `SamDetection`,
  the shared `mask_outline` polygon, `on_usage`, `before_call`, and
  `max_calls_per_session` (default 200).
