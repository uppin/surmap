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
- Model id: `sam-3.1` by default (`model=`). The only rejected ids
  are those containing `wonder-full` or `wonder_full` (any case).
  That is Muse Wonder Full, the uncovered credit. Other ids may
  contain `wonder`.
- Prompt: a short noun phrase (`prompt=`, default `object`). One
  concept per request, matching the SAM docs.
- Image: an mjpeg frame is sent as its jpeg bytes. A raw RGB frame
  is encoded as PNG. Both go out as a base64 data URL on
  `input_image`.
- `stream` is false.
- Metadata (string values, as the docs require):
  `include_confidence=true`, `mask_encoding=one_bit`.
- Each detector instance allows `max_calls_per_session` requests
  (default 5000). Set `SURMAP_META_SAM_MAX_CALLS` to override that
  default. An explicit `max_calls_per_session=` argument wins over
  the env var. The next call past the cap raises `MetaSamCallLimit`
  and does not touch the network. A send that fails still counts.
  A `before_call` that raises does not. `before_call` stays in
  front of every counted request.
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

## Verified live

On 2026-11-02 `scripts/check_meta_sam.py` sent one LADI v2 aerial
image (CC BY 4.0) with the prompt `building` to `sam-3.1` and got 25
detections, scores 0.54 to 0.86, each with a box and a mask. The
response confirmed what was earlier inferred from a text Responses
call:

- A non-streaming SAM response uses the Responses JSON envelope: the
  grammar arrives as `output[].content[]` blocks with
  `type: output_text`.
- `usage` carries `input_tokens`, `output_tokens` and
  `output_tokens_details.reasoning_tokens` (all `0` for SAM) plus
  `images_processed`. A missing reasoning field is `None`, not zero.
- The request with `type: message` on the input item, as in the SAM
  segmenting examples, is accepted.

An image with nothing matching the prompt (the 32×32 default fixture)
returns one empty `output_text` block, which parses as no detections.

The grammar itself (frame marker, inclusive box, base85 mask) is
the documented one. The request's model id, URL, bearer auth, and
`input_text` / `input_image` parts are the documented ones.

## One live call from WSL

From the repository root inside WSL. This sends one image
(`scripts/fixtures/meta_sam_check.png`) with prompt `person`, prints
the detections, and writes the response JSON to
`tmp/meta-sam-last-response.json`. That path is gitignored. The API
key is not printed. If the key string appears in the response, it is
replaced with `[redacted]` in the file; the rest of the body is kept
so the wire format can be checked.

```bash
SURMAP_LIVE_META=1 MODEL_API_KEY='paste-key-here' uv run python scripts/check_meta_sam.py
```

`--image` and `--prompt` override the defaults. The script does not
call Meta unless both `SURMAP_LIVE_META=1` and `MODEL_API_KEY` are set.
