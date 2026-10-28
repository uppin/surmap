"""Per-object labels from Baseten Muse Spark Open.

The live call is opt-in. Tests pass a transport and never open a socket.
Reasoning stays on (``reasoning_effort`` defaults to ``low``, or
``SURMAP_BASETEN_REASONING_EFFORT`` when set to low, medium, or high).
The client does not send a flag that claims reasoning is off, and it
does not ask for JSON mode. ``max_tokens`` caps the completion,
including reasoning tokens (default 1024, or ``SURMAP_BASETEN_MAX_TOKENS``).
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast, runtime_checkable

from surmap.types import Vec3
from surmap.usage import UsageLedger, UsageRecord

DEFAULT_MODEL_ID = "meta-models/muse-spark-open-1026"
DEFAULT_REASONING_EFFORT = "low"
DEFAULT_MAX_TOKENS = 1024
_COMPLETIONS_URL = "https://inference.baseten.co/v1/chat/completions"
_ALLOWED_EFFORT = frozenset({"low", "medium", "high"})
_EFFORT_ENV = "SURMAP_BASETEN_REASONING_EFFORT"
_MAX_TOKENS_ENV = "SURMAP_BASETEN_MAX_TOKENS"
_SYSTEM_PROMPT = (
    "You label one object in a civilian disaster-survey photo. Reply in plain text, not JSON."
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


class BasetenApiKeyMissing(RuntimeError):
    """Raised before any request when ``BASETEN_API_KEY`` is missing or blank."""


class BasetenRequestError(RuntimeError):
    """The chat-completions call failed or the body was not a completion."""


@dataclass(frozen=True)
class ObjectLabel:
    """One crop's label. ``raw_text`` is assistant content, never the reasoning trace."""

    label: str
    description: str
    confidence: float | None
    model_id: str
    raw_text: str
    reasoning_text: str | None = None


@runtime_checkable
class LabelClient(Protocol):
    def label(self, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel: ...


class ChatTransport(Protocol):
    """HTTP seam. The default posts with urllib; tests record the body instead."""

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes: ...


class BasetenMuseLabelClient:
    """``LabelClient`` backed by Baseten chat completions."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str = DEFAULT_MODEL_ID,
        transport: ChatTransport | None = None,
        ledger: UsageLedger | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int | None = None,
        clock: Callable[[], float] | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._model_id = model_id
        self._transport = transport
        self._ledger = ledger
        self._reasoning_effort = _resolve_reasoning_effort(reasoning_effort)
        self._max_tokens = _resolve_max_tokens(max_tokens)
        self._clock = time.time if clock is None else clock
        self._timeout_s = timeout_s

    def label(self, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel:
        api_key = self._resolve_api_key()
        if self._ledger is not None:
            self._ledger.check("baseten")
        body = json.dumps(self._payload(jpeg, coarse_label, xyz)).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        raw = self._transport_for_call().post(_COMPLETIONS_URL, headers, body)
        response = _json_object(raw)
        labelled = _object_label(response, requested_model=self._model_id)
        if self._ledger is not None:
            prompt_tokens, completion_tokens, reasoning_tokens = _usage_counts(response)
            self._ledger(
                UsageRecord(
                    "baseten",
                    labelled.model_id,
                    prompt_tokens,
                    completion_tokens,
                    reasoning_tokens,
                    self._clock(),
                )
            )
        return labelled

    def _resolve_api_key(self) -> str:
        raw = self._api_key if self._api_key is not None else os.environ.get("BASETEN_API_KEY")
        key = (raw or "").strip()
        if not key:
            raise BasetenApiKeyMissing(
                "BASETEN_API_KEY is not set. Export it or pass api_key= to "
                "BasetenMuseLabelClient. Do not commit the key; the repo is public."
            )
        return key

    def _transport_for_call(self) -> ChatTransport:
        if self._transport is not None:
            return self._transport
        return _UrllibChatTransport(self._timeout_s)

    def _payload(self, jpeg: bytes, coarse_label: str, xyz: Vec3) -> dict[str, object]:
        encoded = base64.b64encode(jpeg).decode("ascii")
        image_part: dict[str, object] = {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
        }
        text_part: dict[str, object] = {"type": "text", "text": _user_text(coarse_label, xyz)}
        user_message: dict[str, object] = {
            "role": "user",
            "content": [image_part, text_part],
        }
        system_message: dict[str, object] = {"role": "system", "content": _SYSTEM_PROMPT}
        return {
            "model": self._model_id,
            "messages": [system_message, user_message],
            "reasoning_effort": self._reasoning_effort,
            "max_tokens": self._max_tokens,
        }


def _resolve_reasoning_effort(explicit: str | None) -> str:
    """Constructor argument wins. Otherwise ``SURMAP_BASETEN_REASONING_EFFORT``, else low."""
    if explicit is not None:
        raw = explicit
    else:
        raw = os.environ.get(_EFFORT_ENV, "").strip() or DEFAULT_REASONING_EFFORT
    effort = raw.strip().lower()
    if effort not in _ALLOWED_EFFORT:
        raise ValueError(
            "reasoning_effort must be low, medium, or high "
            f"({_EFFORT_ENV}); Muse Spark Open cannot turn reasoning off"
        )
    return effort


def _resolve_max_tokens(explicit: int | None) -> int:
    """Constructor argument wins. Otherwise ``SURMAP_BASETEN_MAX_TOKENS``, else 1024."""
    if explicit is not None:
        if isinstance(explicit, bool) or explicit <= 0:
            raise ValueError("max_tokens must be a positive integer")
        return explicit
    raw = os.environ.get(_MAX_TOKENS_ENV, "").strip()
    if not raw:
        return DEFAULT_MAX_TOKENS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{_MAX_TOKENS_ENV} must be a positive integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{_MAX_TOKENS_ENV} must be a positive integer, got {raw!r}")
    return value


def _user_text(coarse_label: str, xyz: Vec3) -> str:
    return (
        f"On-board detector label: {coarse_label}\n"
        f"Map-frame centroid in metres: x={xyz.x:.2f} y={xyz.y:.2f} z={xyz.z:.2f}\n"
        "\n"
        "Use these lines:\n"
        "label: <short noun phrase>\n"
        "confidence: <number from 0 to 1, or omit the line>\n"
        "description: <one sentence>\n"
    )


class _UrllibChatTransport:
    def __init__(self, timeout_s: float) -> None:
        self._timeout_s = timeout_s

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        request = urllib.request.Request(
            url,
            data=body,
            headers={str(key): value for key, value in headers.items()},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise BasetenRequestError(
                f"Baseten chat completions returned HTTP {exc.code}: {detail[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise BasetenRequestError(
                f"Baseten chat completions request failed: {exc.reason}"
            ) from exc
        if not isinstance(payload, bytes):
            raise BasetenRequestError("Baseten response body was not bytes")
        return payload


def _json_object(raw: bytes) -> dict[str, object]:
    try:
        parsed: object = cast(object, json.loads(raw))
    except json.JSONDecodeError as exc:
        raise BasetenRequestError("Baseten response was not JSON") from exc
    return _as_dict(parsed, "response")


def _as_dict(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise BasetenRequestError(f"Baseten {what} was not a JSON object")
    return {str(key): item for key, item in value.items()}


def _object_label(response: dict[str, object], *, requested_model: str) -> ObjectLabel:
    message = _message(response)
    content = message.get("content")
    if content is None:
        raw_text = ""
    elif isinstance(content, str):
        raw_text = content
    else:
        raise BasetenRequestError("Baseten message content was not text")
    reasoning = message.get("reasoning_content")
    reasoning_text = reasoning if isinstance(reasoning, str) else None
    label, description = _label_and_description(raw_text)
    served = response.get("model")
    model_id = served.strip() if isinstance(served, str) and served.strip() else requested_model
    return ObjectLabel(
        label=label,
        description=description,
        confidence=_confidence(raw_text),
        model_id=model_id,
        raw_text=raw_text,
        reasoning_text=reasoning_text,
    )


def _message(response: dict[str, object]) -> dict[str, object]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise BasetenRequestError("Baseten response had no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise BasetenRequestError("Baseten response choice was not an object")
    choice = {str(key): value for key, value in first.items()}
    return _as_dict(choice.get("message"), "message")


def _label_and_description(text: str) -> tuple[str, str]:
    label: str | None = None
    description_parts: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if label is None and lower.startswith("label:"):
            label = stripped.split(":", 1)[1].strip()
            continue
        if lower.startswith("confidence:"):
            continue
        if lower.startswith("description:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                description_parts.append(value)
            continue
        description_parts.append(stripped)
    if label is None:
        if not description_parts:
            return "", ""
        label = description_parts[0]
        description_parts = description_parts[1:]
    return label, " ".join(description_parts)


def _confidence(text: str) -> float | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("confidence:"):
            continue
        match = _NUMBER.search(stripped.split(":", 1)[1])
        if match is None:
            return None
        return float(match.group(0))
    match = _NUMBER.search(text)
    if match is None:
        return None
    return float(match.group(0))


def _usage_counts(response: dict[str, object]) -> tuple[int, int, int | None]:
    raw = response.get("usage")
    if raw is None:
        return 0, 0, None
    usage = _as_dict(raw, "usage")
    prompt_tokens = _usage_int(usage.get("prompt_tokens", 0), "prompt_tokens")
    completion_tokens = _usage_int(usage.get("completion_tokens", 0), "completion_tokens")
    details = usage.get("completion_tokens_details")
    if details is None:
        return prompt_tokens, completion_tokens, None
    detail_map = _as_dict(details, "completion_tokens_details")
    reasoning = detail_map.get("reasoning_tokens")
    if reasoning is None:
        return prompt_tokens, completion_tokens, None
    return prompt_tokens, completion_tokens, _usage_int(reasoning, "reasoning_tokens")


def _usage_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BasetenRequestError(f"Baseten usage field {field} was not an integer")
    return value
