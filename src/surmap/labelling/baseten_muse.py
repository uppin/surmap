"""Per-object labels from Baseten Muse Spark Open.

Posts one JPEG crop to `https://inference.baseten.co/v1/chat/completions`.
The model always reasons. This client sends `reasoning_effort: low`
because the provider default is `xhigh`, and it reads the label from
`choices[0].message.content` only. `reasoning_content` is not a label.
The API key is `BASETEN_API_KEY`. It is never logged and never written
into an error message.

The prompt frames a civilian disaster-response survey. The client does
not ask for flight, navigation, or mission actions.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from surmap.labelling.base import ObjectLabel
from surmap.types import Vec3

DEFAULT_MODEL_ID = "meta-models/muse-spark-open-1026"
DEFAULT_BASE_URL = "https://inference.baseten.co/v1"
DEFAULT_REASONING_EFFORT = "low"
_CHAT_PATH = "/chat/completions"

_LABEL_LINE = re.compile(r"(?im)^\s*label\s*:\s*(.+?)\s*$")
_CONFIDENCE = re.compile(r"(?i)confidence\s*:\s*(\d+(?:\.\d+)?)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")

_SYSTEM_PROMPT = (
    "You label a single object for a civilian disaster-response survey. "
    "The camera was carried passively over an affected area so a "
    "search-and-rescue team can recognise landmarks, debris, and vehicles. "
    "Describe only what is visible in the crop. Do not propose flight, "
    "navigation, or mission actions. "
    "Reply in plain text, not JSON. "
    "The first line must be 'label: ' and a short noun phrase. "
    "The following lines are one sentence a responder can read. "
    "Include a number only when you state a confidence between 0 and 1, "
    "written as 'confidence: <number>'. Otherwise include no number."
)


class BasetenApiKeyMissing(RuntimeError):
    """`BASETEN_API_KEY` is unset. Raised before any socket is opened."""


class BasetenLabelError(RuntimeError):
    """The Baseten call failed, or the assistant text had no label."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


class HttpTransport(Protocol):
    """One POST. Tests supply a transport that never opens a socket."""

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> HttpResponse: ...


class UrllibTransport:
    """Stdlib transport. Opens a socket only when `post` is called."""

    def __init__(self, timeout_s: float = 120.0) -> None:
        self._timeout_s = timeout_s

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                raw = response.read()
                status = _status_code(response)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        except urllib.error.URLError as exc:
            raise BasetenLabelError("Baseten request failed before a response.") from exc
        if not isinstance(raw, bytes):
            raise BasetenLabelError("Baseten response body was not bytes.")
        return HttpResponse(status, raw)


def _status_code(response: object) -> int:
    status: object = getattr(response, "status", None)
    if not isinstance(status, int):
        raise BasetenLabelError("Baseten response had no HTTP status.")
    return status


def _require_api_key(api_key: str | None, env: Mapping[str, str]) -> str:
    key = api_key if api_key is not None else env.get("BASETEN_API_KEY")
    if key is None or key.strip() == "":
        raise BasetenApiKeyMissing(
            "BASETEN_API_KEY is not set. Export it before constructing "
            "BasetenMuseLabelClient. No request was sent."
        )
    return key.strip()


class BasetenMuseLabelClient:
    """LabelClient that calls Muse Spark Open on Baseten."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str = DEFAULT_MODEL_ID,
        transport: HttpTransport | None = None,
        base_url: str = DEFAULT_BASE_URL,
        env: Mapping[str, str] | None = None,
    ) -> None:
        source = os.environ if env is None else env
        self._api_key = _require_api_key(api_key, source)
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._transport: HttpTransport = transport if transport is not None else UrllibTransport()

    def label_object(self, crop_jpeg: bytes, coarse_label: str, map_xyz: Vec3) -> ObjectLabel:
        if crop_jpeg == b"":
            raise BasetenLabelError("A JPEG crop is required before calling Baseten.")
        body = json.dumps(_payload(crop_jpeg, coarse_label, map_xyz, self._model_id)).encode()
        response = self._transport.post(
            f"{self._base_url}{_CHAT_PATH}",
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            body,
        )
        if response.status != 200:
            raise BasetenLabelError(_http_error(response.status, response.body, self._api_key))
        return _parse_completion(response.body, self._model_id)


def _payload(
    crop_jpeg: bytes, coarse_label: str, map_xyz: Vec3, model_id: str
) -> dict[str, object]:
    encoded = base64.b64encode(crop_jpeg).decode("ascii")
    user_text = (
        f"Coarse detector label: {coarse_label}\n"
        "Map-frame position in metres: "
        f"x={map_xyz.x:.3f} y={map_xyz.y:.3f} z={map_xyz.z:.3f}\n"
        "Name this object for the search-and-rescue team."
    )
    messages: list[dict[str, object]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                },
                {"type": "text", "text": user_text},
            ],
        },
    ]
    return {
        "model": model_id,
        "messages": messages,
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
    }


def _http_error(status: int, body: bytes, api_key: str) -> str:
    detail = body.decode("utf-8", errors="replace").strip()
    if api_key:
        detail = detail.replace(api_key, "[redacted]")
    if len(detail) > 300:
        detail = detail[:300] + "…"
    if detail:
        return f"Baseten chat completions returned HTTP {status}: {detail}"
    return f"Baseten chat completions returned HTTP {status}."


def _parse_completion(body: bytes, model_id: str) -> ObjectLabel:
    text = _assistant_text(_json_object(body))
    label, description = _split_label(text)
    return ObjectLabel(
        label=label,
        description=description,
        confidence=_confidence(text),
        model_id=model_id,
        raw_text=text,
    )


def _json_object(body: bytes) -> dict[str, object]:
    try:
        parsed: object = json.loads(body)
    except json.JSONDecodeError as exc:
        raise BasetenLabelError("Baseten response was not JSON.") from exc
    if not isinstance(parsed, dict):
        raise BasetenLabelError("Baseten response was not a JSON object.")
    return {str(key): value for key, value in parsed.items()}


def _as_mapping(value: object, what: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise BasetenLabelError(f"Baseten response {what} was not an object.")
    return {str(key): item for key, item in value.items()}


def _assistant_text(payload: Mapping[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        raise BasetenLabelError("Baseten response had no choices.")
    first: object = choices[0]
    message = _as_mapping(first, "choice").get("message")
    content = _as_mapping(message, "message").get("content")
    if not isinstance(content, str) or content.strip() == "":
        raise BasetenLabelError(
            "Baseten assistant content was empty. The label is read from "
            "message.content only; reasoning_content is not a label."
        )
    return content.strip()


def _split_label(text: str) -> tuple[str, str]:
    match = _LABEL_LINE.search(text)
    if match is not None:
        label = match.group(1).strip()
        if label == "":
            raise BasetenLabelError("Baseten assistant text had an empty label.")
        remainder = (text[: match.start()] + text[match.end() :]).strip()
        return label, remainder
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise BasetenLabelError("Baseten assistant content had no label line.")
    return lines[0], "\n".join(lines[1:]).strip()


def _confidence(text: str) -> float | None:
    named = _CONFIDENCE.search(text)
    if named is not None:
        return float(named.group(1))
    number = _NUMBER.search(text)
    if number is None:
        return None
    return float(number.group(0))
