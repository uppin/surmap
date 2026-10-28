"""Station SAM 3.1 over the Meta Model API.

`MetaSamDetector` is a `SamDetector`. It posts one frame and a short
noun-phrase prompt to ``POST https://api.meta.ai/v1/responses`` and
maps the returned boxes and masks to `SamDetection`. No checkpoint is
fetched and no separate GPU service is started. The live socket is
used only by `UrllibMetaTransport`; tests pass a fake transport.
`tests/test_meta_sam.py` calls the network only when
``SURMAP_LIVE_META=1``.

Wire format, checked against Meta's public docs on 2026-10-28
(https://dev.meta.ai/docs/sam/segmenting,
https://dev.meta.ai/docs/sam/reading-segmentation,
https://dev.meta.ai/docs/protocols/responses) and against a text
Responses call that returned ``output[]`` plus
``usage.input_tokens`` / ``usage.output_tokens``:

* The model id defaults to ``sam-3.1`` and is configurable. An id
  containing ``wonder`` is rejected.
* The body is a non-streaming Responses request: one user message
  with ``input_text`` (the prompt) and ``input_image`` (a base64
  data URL: the jpeg bytes for an mjpeg frame, a PNG for raw RGB),
  ``stream: false``, and string metadata
  ``include_confidence=true``, ``mask_encoding=one_bit``. The input
  item includes ``type: message``, which the SAM docs show. The
  verified text-call body omitted that field.
* Segmentation text is the documented special-token grammar. Mask
  rasters are decoded with ``meta-sam-parser`` (the documented
  decoder), not a local codec. Wire boxes are inclusive; this module
  stores the half-open box that parser emits, which matches
  `Sam3Detector`. The mask raster is box-local. The polygon is
  `mask_outline` of that raster, shifted onto the box.
* A missing ``c`` field is not a score of zero. Those detections are
  kept with score ``1.0``. ``track_id`` is the wire object id.

Assumed, because a live ``sam-3.1`` response was not captured:

* A non-streaming SAM call uses the same JSON envelope as a text
  Responses call: ``output[].content[]`` blocks of type
  ``output_text``, and ``usage`` with ``input_tokens`` and
  ``output_tokens``. That envelope is isolated in
  `read_responses_body`.
* Reasoning tokens are ``usage.output_tokens_details.reasoning_tokens``
  when that integer is present, and ``None`` when the object is
  absent. The verified text usage had no reasoning field.

`on_usage` is ``(provider, model, input_tokens, output_tokens,
reasoning_tokens)`` with provider ``meta``. `before_call` is invoked
with ``meta`` after the session cap and the API key have been
checked and before the request is counted or sent. It may raise to
stop the call. `max_calls_per_session` (default 200) bounds one
detector instance so a demo replay cannot call the API once per
frame without limit. A failed send still counts. A blocked
`before_call` does not.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Protocol

import numpy as np
from meta_sam_parser import (
    CompletedOutcome,
    SegmentationBoxRecord,
    SegmentationMaskRecord,
    SegmentationTextRecord,
    decode_mask_to_raster,
    image_segmentation_format,
)
from PIL import Image

from surmap.survey.sam import RawFrame, SamDetection
from surmap.survey.sam3 import mask_outline

DEFAULT_ENDPOINT = "https://api.meta.ai/v1/responses"
DEFAULT_MODEL = "sam-3.1"
DEFAULT_MAX_CALLS_PER_SESSION = 200
DEFAULT_PROMPT = "object"

UsageCallback = Callable[[str, str, int, int, int | None], None]
BeforeCall = Callable[[str], None]


class MetaSamError(RuntimeError):
    """The Meta Model API SAM call could not be completed."""


class MetaSamCallLimit(MetaSamError):
    """This detector has used its session call budget."""


class MetaResponsesTransport(Protocol):
    """One JSON POST. Tests supply a fake; production uses urllib."""

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> Mapping[str, object]: ...


class UrllibMetaTransport:
    """`MetaResponsesTransport` over the stdlib HTTP client."""

    def __init__(self, timeout_s: float = 60.0) -> None:
        self._timeout_s = timeout_s

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers=dict(headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise MetaSamError(f"Meta Model API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MetaSamError(f"Meta Model API request failed: {exc.reason}") from exc
        return _json_object(raw)


def sam_responses_payload(model: str, prompt: str, image_data_url: str) -> dict[str, object]:
    """The documented non-streaming SAM 3.1 request body."""
    content: list[dict[str, object]] = [
        {"type": "input_text", "text": prompt},
        {"type": "input_image", "image_url": image_data_url},
    ]
    message: dict[str, object] = {
        "type": "message",
        "role": "user",
        "content": content,
    }
    return {
        "model": model,
        "input": [message],
        "stream": False,
        "metadata": {
            "include_confidence": "true",
            "mask_encoding": "one_bit",
        },
    }


def read_responses_body(body: Mapping[str, object]) -> tuple[str, int, int, int | None]:
    """Split a Responses JSON object into text and token counts.

    This is the envelope assumed for SAM from text Responses calls:
    ``output_text`` blocks, ``input_tokens``, ``output_tokens``, and
    optional ``output_tokens_details.reasoning_tokens``.
    """
    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        detail = message if isinstance(message, str) else "Meta Model API returned an error"
        raise MetaSamError(detail)
    status = body.get("status")
    if isinstance(status, str) and status != "completed":
        raise MetaSamError(f"Meta Model API status is {status}")
    text = _output_text(body)
    usage = body.get("usage")
    if usage is None:
        return text, 0, 0, None
    if not isinstance(usage, dict):
        raise MetaSamError("Meta usage is not an object")
    return text, _count(usage, "input_tokens"), _count(usage, "output_tokens"), _reasoning(usage)


def detections_from_output_text(
    text: str,
    *,
    label: str,
    score_threshold: float = 0.0,
) -> tuple[SamDetection, ...]:
    """Map one image's SAM output-text grammar to `SamDetection` values.

    Empty text is zero matches. Prose, or a line the SAM parser rejects,
    raises `MetaSamError` instead of looking like a miss.
    """
    if text.strip() == "":
        return ()
    parser = image_segmentation_format().create_parser()
    parser.push(text)
    result = parser.finish(CompletedOutcome()).result
    errors = [item.message for item in result.diagnostics if item.severity == "error"]
    if errors:
        raise MetaSamError(f"SAM output error: {errors[0]}")
    boxes: dict[str, SegmentationBoxRecord] = {}
    masks: dict[str, SegmentationMaskRecord] = {}
    saw_text = False
    for record in result.records:
        if isinstance(record, SegmentationBoxRecord):
            boxes[record.object_id] = record
        elif isinstance(record, SegmentationMaskRecord):
            masks[record.object_id] = record
        elif isinstance(record, SegmentationTextRecord):
            saw_text = True
    if saw_text and not masks:
        raise MetaSamError("SAM output was not segmentation records")
    detections: list[SamDetection] = []
    for object_id, mask_record in masks.items():
        box = boxes.get(object_id)
        if box is None:
            continue
        score = _score(box, mask_record)
        if score < score_threshold:
            continue
        detections.append(
            SamDetection(
                label=label,
                score=score,
                box_xyxy=(box.left, box.top, box.right, box.bottom),
                mask_polygon=_polygon(mask_record),
                track_id=_track_id(object_id),
            )
        )
    return tuple(detections)


class MetaSamDetector:
    """`SamDetector` adapter over the Meta Model API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        prompt: str = DEFAULT_PROMPT,
        endpoint: str = DEFAULT_ENDPOINT,
        transport: MetaResponsesTransport | None = None,
        on_usage: UsageCallback | None = None,
        before_call: BeforeCall | None = None,
        max_calls_per_session: int = DEFAULT_MAX_CALLS_PER_SESSION,
        score_threshold: float = 0.0,
        timeout_s: float = 60.0,
    ) -> None:
        if max_calls_per_session < 1:
            raise ValueError("max_calls_per_session must be at least 1")
        self._api_key = api_key
        self._model = _require_model(model)
        self._prompt = prompt
        self._endpoint = endpoint
        self._transport = transport if transport is not None else UrllibMetaTransport(timeout_s)
        self._on_usage = on_usage
        self._before_call = before_call
        self._max_calls = max_calls_per_session
        self._score_threshold = score_threshold
        self._calls = 0
        self._lock = threading.Lock()

    @property
    def calls_made(self) -> int:
        """How many requests this detector has counted."""
        return self._calls

    @property
    def max_calls_per_session(self) -> int:
        return self._max_calls

    @property
    def model(self) -> str:
        return self._model

    async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        """Segment one frame (the HTTP call runs off the event loop)."""
        return await asyncio.to_thread(self._detect_sync, frame)

    def _detect_sync(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        image_url = _frame_image_data_url(frame)
        payload = sam_responses_payload(self._model, self._prompt, image_url)
        with self._lock:
            if self._calls >= self._max_calls:
                raise MetaSamCallLimit(f"Meta SAM session call limit is {self._max_calls}")
            secret = self._resolve_key()
            if self._before_call is not None:
                self._before_call("meta")
            self._calls += 1
            headers = {
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            try:
                body = self._transport.post(self._endpoint, headers, payload)
            except Exception as exc:
                raise MetaSamError(_redact(str(exc), secret)) from exc
        text, incoming, outgoing, reasoning = read_responses_body(body)
        if self._on_usage is not None:
            self._on_usage("meta", self._model, incoming, outgoing, reasoning)
        return detections_from_output_text(
            text, label=self._prompt, score_threshold=self._score_threshold
        )

    def _resolve_key(self) -> str:
        key = self._api_key if self._api_key is not None else os.environ.get("MODEL_API_KEY")
        if key is None or key == "":
            raise MetaSamError("MODEL_API_KEY is not set")
        return key


def _require_model(model: str) -> str:
    stripped = model.strip()
    if not stripped or "wonder" in stripped.casefold():
        raise ValueError(f"unsupported Meta model id: {model!r}")
    return stripped


def _frame_image_data_url(frame: RawFrame) -> str:
    if frame.encoding == "mjpeg":
        payload = frame.data
        mime = "image/jpeg"
    elif frame.encoding == "raw_rgb":
        expected = frame.width * frame.height * 3
        if len(frame.data) != expected:
            raise MetaSamError(f"raw_rgb frame has {len(frame.data)} bytes, expected {expected}")
        image = Image.frombytes("RGB", (frame.width, frame.height), frame.data)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        payload = buffer.getvalue()
        mime = "image/png"
    else:
        raise MetaSamError(f"unsupported frame encoding: {frame.encoding}")
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _output_text(body: Mapping[str, object]) -> str:
    output = body.get("output")
    if not isinstance(output, list) or not output:
        raise MetaSamError("Meta response has no output list")
    parts: list[str] = []
    found = False
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "output_text":
                continue
            text = block.get("text")
            if isinstance(text, str):
                found = True
                parts.append(text)
    if not found:
        raise MetaSamError("Meta response has no output_text")
    return "".join(parts)


def _count(usage: Mapping[str, object], key: str) -> int:
    value = usage.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetaSamError(f"Meta {key} is not an integer")
    return value


def _reasoning(usage: Mapping[str, object]) -> int | None:
    details = usage.get("output_tokens_details")
    if details is None:
        return None
    if not isinstance(details, dict):
        raise MetaSamError("Meta output_tokens_details is not an object")
    if "reasoning_tokens" not in details:
        return None
    value = details["reasoning_tokens"]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetaSamError("Meta reasoning_tokens is not an integer")
    return value


def _score(box: SegmentationBoxRecord, mask_record: SegmentationMaskRecord) -> float:
    if box.confidence is not None:
        return box.confidence
    if mask_record.confidence is not None:
        return mask_record.confidence
    return 1.0


def _track_id(object_id: str) -> int | None:
    if object_id.isascii() and object_id.isdigit():
        return int(object_id)
    return None


def _polygon(record: SegmentationMaskRecord) -> tuple[tuple[float, float], ...]:
    raster = decode_mask_to_raster(record.mask)
    flat = np.frombuffer(raster, dtype=np.uint8)
    mask = np.asarray(flat.reshape(record.mask.height, record.mask.width) != 0)
    bounds = record.bounds
    scale_x = (bounds.right - bounds.left) / record.mask.width
    scale_y = (bounds.bottom - bounds.top) / record.mask.height
    outline = mask_outline(mask, scale_x, scale_y)
    return tuple((x + bounds.left, y + bounds.top) for x, y in outline)


def _json_object(raw: bytes) -> dict[str, object]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MetaSamError("Meta Model API returned non-JSON") from exc
    if not isinstance(parsed, dict):
        raise MetaSamError("Meta Model API returned a non-object JSON body")
    body: dict[str, object] = {}
    for key, value in parsed.items():
        if not isinstance(key, str):
            raise MetaSamError("Meta Model API returned a non-object JSON body")
        body[key] = value
    return body


def _redact(message: str, secret: str) -> str:
    if secret and secret in message:
        return message.replace(secret, "[redacted]")
    return message
