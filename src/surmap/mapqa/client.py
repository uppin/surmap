"""Meta Model API calls for Ask the map.

Responses: ``POST https://api.meta.ai/v1/responses``.
Transcription: ``POST https://api.meta.ai/v1/asr/transcribe``.

Tests pass a transport and never open a socket. A blank reply is retried
once. Muse Wonder Full is refused before any request: it is not served on
this API.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Protocol, cast

from surmap.mapqa.answers import ModelUsage
from surmap.mapqa.errors import (
    EmptyModelOutput,
    ModelApiError,
    ModelApiKeyMissing,
    WonderFullRefused,
)

DEFAULT_MODEL = "muse-wonder-1.0"
VOICE_MODEL = "muse-voice-transcribe-1.0"
MIN_MAX_OUTPUT_TOKENS = 8192
RESPONSES_URL = "https://api.meta.ai/v1/responses"
TRANSCRIBE_URL = "https://api.meta.ai/v1/asr/transcribe"
_MODEL_ENV = "SURMAP_MAPQA_MODEL"
_KEY_ENV = "MODEL_API_KEY"

BeforeCall = Callable[[str, Mapping[str, object]], None]
OnUsage = Callable[[ModelUsage], None]
Clock = Callable[[], float]

_AUTO_LEDGER = object()


class HttpTransport(Protocol):
    """HTTP seam. The default posts with urllib."""

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes: ...


class _LedgerSink(Protocol):
    """The slice of ``UsageLedger`` Ask the map calls. Present only when that module imports."""

    def check(self, provider: str) -> None: ...

    def __call__(self, record: object) -> None: ...


class UrllibTransport:
    """POST a body and return the response bytes."""

    def __init__(self, timeout_s: float) -> None:
        self._timeout_s = timeout_s

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ModelApiError(f"Meta Model API returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ModelApiError(f"Meta Model API request failed: {exc.reason}") from exc
        if not isinstance(payload, bytes):
            raise ModelApiError("Meta Model API returned no body")
        return payload


class MetaClient:
    """One configured model, shared by ask, report, and voice."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        transport: HttpTransport | None,
        before_call: BeforeCall | None,
        on_usage: OnUsage | None,
        usage_ledger: object | None,
        max_output_tokens: int,
        clock: Clock | None,
        timeout_s: float,
    ) -> None:
        self.model = resolve_model(model)
        self._max_output_tokens = _resolve_max_output_tokens(max_output_tokens)
        self._api_key = api_key
        self._transport = transport
        self._timeout_s = timeout_s
        self._before_call = before_call
        self._on_usage = on_usage
        self._clock = time.time if clock is None else clock
        if usage_ledger is _AUTO_LEDGER:
            self._ledger: object | None = _default_ledger()
        else:
            self._ledger = usage_ledger

    def complete(self, instructions: str, user_text: str) -> str:
        """One responses call. A blank ``output_text`` is sent again once."""
        key = resolve_api_key(self._api_key)
        payload: dict[str, object] = {
            "model": self.model,
            "reasoning": {"effort": "high"},
            "max_output_tokens": self._max_output_tokens,
            "instructions": instructions,
            "input": user_text,
        }
        text = ""
        usage = ModelUsage(self.model, 0, 0, None)
        for _attempt in range(2):
            self._notify(self.model, payload)
            parsed = self._post_json(RESPONSES_URL, key, payload)
            usage = _usage(parsed, self.model)
            self._emit(usage)
            text = _output_text(parsed)
            if text.strip():
                return text
        raise EmptyModelOutput(
            "Meta Model API returned no output text after one retry "
            f"(input_tokens={usage.input_tokens}, output_tokens={usage.output_tokens}, "
            f"reasoning_tokens={usage.reasoning_tokens})"
        )

    def transcribe(self, audio: bytes, filename: str) -> str:
        """Transcribe one WAV clip. A blank transcript is uploaded again once."""
        key = resolve_api_key(self._api_key)
        fields: dict[str, object] = {
            "model": VOICE_MODEL,
            "audioEncoding": "WAV",
            "mode": "PUSH_TO_TALK",
        }
        transcript = ""
        for _attempt in range(2):
            self._notify(VOICE_MODEL, fields)
            self._ledger_check()
            parsed = self._post_audio(key, fields, audio, filename)
            transcript = _transcript(parsed)
            if transcript.strip():
                return transcript.strip()
        raise EmptyModelOutput("Muse Voice Transcribe returned an empty transcript after one retry")

    def _notify(self, model: str, payload: Mapping[str, object]) -> None:
        if self._before_call is not None:
            self._before_call(model, payload)

    def _emit(self, usage: ModelUsage) -> None:
        if self._on_usage is not None:
            self._on_usage(usage)
        ledger = self._ledger
        if ledger is None:
            return
        record = _usage_record(usage, self._clock())
        if record is None:
            return
        cast(_LedgerSink, ledger)(record)

    def _post_json(self, url: str, key: str, payload: Mapping[str, object]) -> dict[str, object]:
        self._ledger_check()
        raw = self._transport_for_call().post(
            url,
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json.dumps(payload).encode("utf-8"),
        )
        return _json_object(raw)

    def _post_audio(
        self,
        key: str,
        fields: Mapping[str, object],
        audio: bytes,
        filename: str,
    ) -> dict[str, object]:
        body, content_type = _multipart(json.dumps(fields), audio, filename)
        raw = self._transport_for_call().post(
            TRANSCRIBE_URL,
            {
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
                "Content-Type": content_type,
            },
            body,
        )
        return _json_object(raw)

    def _ledger_check(self) -> None:
        ledger = self._ledger
        if ledger is None:
            return
        cast(_LedgerSink, ledger).check("meta")

    def _transport_for_call(self) -> HttpTransport:
        if self._transport is not None:
            return self._transport
        return UrllibTransport(self._timeout_s)


def resolve_model(explicit: str | None) -> str:
    """Constructor model wins. Otherwise ``SURMAP_MAPQA_MODEL``, else Muse Wonder."""
    if explicit is not None:
        raw = explicit
    else:
        raw = os.environ.get(_MODEL_ENV, "")
    model = raw.strip() or DEFAULT_MODEL
    if _is_wonder_full(model):
        raise WonderFullRefused(
            "Muse Wonder Full is not available on the Meta Model API. "
            f"Refusing {model!r} because it names wonder-full. "
            f"Set {_MODEL_ENV} to {DEFAULT_MODEL}."
        )
    return model


def resolve_api_key(explicit: str | None) -> str:
    """Constructor key wins. Otherwise ``MODEL_API_KEY``. Never log the value."""
    raw = explicit if explicit is not None else os.environ.get(_KEY_ENV)
    key = (raw or "").strip()
    if not key:
        raise ModelApiKeyMissing(
            "MODEL_API_KEY is not set. Export it in the shell. Do not commit the key."
        )
    return key


def _resolve_max_output_tokens(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < MIN_MAX_OUTPUT_TOKENS:
        raise ValueError(
            f"max_output_tokens must be an integer >= {MIN_MAX_OUTPUT_TOKENS} "
            "so reasoning effort high still has room for the answer"
        )
    return value


def _is_wonder_full(model: str) -> bool:
    folded = model.strip().lower().replace("_", "-").replace(" ", "-")
    while "--" in folded:
        folded = folded.replace("--", "-")
    return "wonder-full" in folded


def _json_object(raw: bytes) -> dict[str, object]:
    try:
        parsed: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelApiError("Meta Model API returned a body that is not JSON") from exc
    if not isinstance(parsed, dict):
        raise ModelApiError("Meta Model API returned JSON that is not an object")
    return {str(key): value for key, value in parsed.items()}


def _output_text(payload: Mapping[str, object]) -> str:
    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        row = {str(key): value for key, value in item.items()}
        if row.get("type") != "message":
            continue
        content = row.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            piece = {str(key): value for key, value in block.items()}
            if piece.get("type") != "output_text":
                continue
            text = piece.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _usage(payload: Mapping[str, object], model: str) -> ModelUsage:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return ModelUsage(model, 0, 0, None)
    row = {str(key): value for key, value in usage.items()}
    return ModelUsage(
        model,
        _token_count(row.get("input_tokens")),
        _token_count(row.get("output_tokens")),
        _reasoning_tokens(row.get("output_tokens_details")),
    )


def _reasoning_tokens(value: object) -> int | None:
    if not isinstance(value, dict):
        return None
    row = {str(key): item for key, item in value.items()}
    count = row.get("reasoning_tokens")
    if isinstance(count, bool) or not isinstance(count, int):
        return None
    return count


def _token_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _transcript(payload: Mapping[str, object]) -> str:
    value = payload.get("transcript")
    if not isinstance(value, str):
        raise ModelApiError("transcription response has no transcript string")
    return value


def _multipart(request_json: str, audio: bytes, filename: str) -> tuple[bytes, str]:
    boundary = "surmap-mapqa-boundary"
    safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "") or "audio.wav"
    crlf = b"\r\n"
    parts = [
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="request"',
        b"Content-Type: application/json",
        b"",
        request_json.encode("utf-8"),
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="audio"; filename="{safe_name}"'.encode(),
        b"Content-Type: audio/wav",
        b"",
        audio,
        f"--{boundary}--".encode(),
        b"",
    ]
    return crlf.join(parts), f"multipart/form-data; boundary={boundary}"


def _default_ledger() -> object | None:
    module = _usage_module()
    if module is None:
        return None
    ledger_cls = getattr(module, "UsageLedger", None)
    if not callable(ledger_cls):
        return None
    return cast(object, ledger_cls())


def _usage_record(usage: ModelUsage, t_unix: float) -> object | None:
    module = _usage_module()
    if module is None:
        return None
    record_cls = getattr(module, "UsageRecord", None)
    if not callable(record_cls):
        return None
    return cast(
        object,
        record_cls(
            "meta",
            usage.model,
            usage.input_tokens,
            usage.output_tokens,
            usage.reasoning_tokens,
            t_unix,
        ),
    )


def _usage_module() -> object | None:
    import importlib

    try:
        return importlib.import_module("surmap.usage")
    except ImportError:
        return None
