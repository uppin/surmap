"""Labels and chat via a Modal shared endpoint for Muse Spark Open.

The endpoint is OpenAI-compatible Chat Completions. Authentication is
a workspace proxy token, ``Authorization: Bearer <id>.<secret>``.
This module does not import the Modal SDK. A missing URL or token
raises before any request.

``label(jpeg, hint)`` is the two-argument form of a label client.
``chat(messages)`` posts an arbitrary message list. ``max_tokens``
defaults to 4096. An empty body or a ``finish_reason`` of ``length``
is retried once with at least twice the cap.

``before_call('modal')`` and ``on_usage`` match ``surmap.survey.modal_sam``:
a plain callback, or a ``surmap.usage.UsageLedger`` duck-typed via
``check`` and a one-argument record call. Token counts come from the
response. GPU seconds are not part of this API.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

DEFAULT_MODEL = "meta-models/Muse-Spark-Open-816B-A42B"
MIN_MAX_TOKENS = 4096

UsageHook = Callable[[str, str, int, int, int | None], None]
BeforeCall = Callable[[str], None]


class ModalMuseConfigError(RuntimeError):
    """Raised before any request when the endpoint URL or proxy token is missing."""


class ModalMuseRequestError(RuntimeError):
    """The chat-completions call failed or the body was not a completion."""


class _LedgerCheck(Protocol):
    def check(self, provider: str) -> None: ...


@dataclass(frozen=True)
class _CreditUse:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None
    t_unix: float


class MuseTransport(Protocol):
    """HTTP seam. The default posts with urllib; tests record the body instead."""

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes: ...


class ModalMuseClient:
    """Chat and one-crop labels against a Modal Muse Spark Open endpoint."""

    def __init__(
        self,
        *,
        url: str | None = None,
        token_id: str | None = None,
        token_secret: str | None = None,
        model: str | None = None,
        transport: MuseTransport | None = None,
        before_call: BeforeCall | _LedgerCheck | None = None,
        on_usage: UsageHook | _LedgerCheck | None = None,
        max_tokens: int = MIN_MAX_TOKENS,
        timeout_s: float = 120.0,
    ) -> None:
        if isinstance(max_tokens, bool) or max_tokens < MIN_MAX_TOKENS:
            raise ValueError(f"max_tokens must be at least {MIN_MAX_TOKENS}")
        self._url = url
        self._token_id = token_id
        self._token_secret = token_secret
        self._model = model
        self._transport = transport
        self._before_call = _bind_before(before_call)
        self._on_usage = _bind_usage(on_usage)
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s

    def label(self, jpeg: bytes, hint: str) -> str:
        """One crop. ``hint`` is the coarse detector label. Returns assistant text."""
        encoded = base64.b64encode(jpeg).decode("ascii")
        media = "image/png" if jpeg.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
        content: list[dict[str, object]] = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media};base64,{encoded}"},
            },
            {
                "type": "text",
                "text": (
                    f"Coarse detector hint: {hint}\n"
                    "Reply with a short noun phrase for this object and one sentence."
                ),
            },
        ]
        messages: list[dict[str, object]] = [{"role": "user", "content": content}]
        return self.chat(messages)

    def chat(self, messages: list[dict[str, object]], *, max_tokens: int | None = None) -> str:
        """POST chat completions. Retries once when the reply is empty or truncated."""
        endpoint, token, model = self._require_config()
        limit = self._max_tokens if max_tokens is None else max_tokens
        if isinstance(limit, bool) or limit < MIN_MAX_TOKENS:
            raise ValueError(f"max_tokens must be at least {MIN_MAX_TOKENS}")
        text = ""
        for attempt in range(2):
            if self._before_call is not None:
                self._before_call("modal")
            body = json.dumps({"model": model, "messages": messages, "max_tokens": limit}).encode(
                "utf-8"
            )
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            raw = self._transport_for_call().post(endpoint, headers, body)
            text, finish, prompt_tokens, completion_tokens, reasoning, served = _completion(raw)
            if self._on_usage is not None:
                self._on_usage(
                    "modal",
                    served or model,
                    prompt_tokens,
                    completion_tokens,
                    reasoning,
                )
            if attempt == 0 and (not text.strip() or finish == "length"):
                limit = max(limit * 2, MIN_MAX_TOKENS * 2)
                continue
            return text
        return text

    def _require_config(self) -> tuple[str, str, str]:
        url = _setting(self._url, "MODAL_MUSE_URL")
        token_id = _setting(self._token_id, "MODAL_PROXY_TOKEN_ID")
        token_secret = _setting(self._token_secret, "MODAL_PROXY_TOKEN_SECRET")
        model = _setting(self._model, "MODAL_MUSE_MODEL") or DEFAULT_MODEL
        if not url or not token_id or not token_secret:
            missing = [
                name
                for name, value in (
                    ("MODAL_MUSE_URL", url),
                    ("MODAL_PROXY_TOKEN_ID", token_id),
                    ("MODAL_PROXY_TOKEN_SECRET", token_secret),
                )
                if not value
            ]
            raise ModalMuseConfigError(
                "Refusing to call Modal before any request; missing " + ", ".join(missing)
            )
        return completions_url(url), f"{token_id}.{token_secret}", model

    def _transport_for_call(self) -> MuseTransport:
        if self._transport is not None:
            return self._transport
        return _UrllibMuseTransport(self._timeout_s)


def completions_url(base: str) -> str:
    """``<endpoint>/v1/chat/completions``, without doubling a suffix already present."""
    trimmed = base.strip().rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed
    if trimmed.endswith("/v1"):
        return trimmed + "/chat/completions"
    return trimmed + "/v1/chat/completions"


def _setting(explicit: str | None, env_name: str) -> str:
    if explicit is not None:
        return explicit.strip()
    return os.environ.get(env_name, "").strip()


def _completion(raw: bytes) -> tuple[str, str | None, int, int, int | None, str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModalMuseRequestError("Modal Muse response was not JSON") from exc
    if not isinstance(payload, dict):
        raise ModalMuseRequestError("Modal Muse response was not a JSON object")
    body = cast(dict[str, Any], payload)
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ModalMuseRequestError("Modal Muse response had no choices")
    choice = cast(dict[str, Any], choices[0])
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ModalMuseRequestError("Modal Muse response choice had no message")
    content = cast(dict[str, Any], message).get("content")
    text = _text(content)
    finish = choice.get("finish_reason")
    finish_reason = finish if isinstance(finish, str) else None
    usage = body.get("usage")
    prompt_tokens, completion_tokens, reasoning = _usage(usage)
    served = body.get("model")
    model = served.strip() if isinstance(served, str) else ""
    return text, finish_reason, prompt_tokens, completion_tokens, reasoning, model


def _text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = cast(dict[str, Any], block).get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    raise ModalMuseRequestError("Modal Muse message content was not text")


def _usage(usage: object) -> tuple[int, int, int | None]:
    if not isinstance(usage, dict):
        return 0, 0, None
    body = cast(dict[str, Any], usage)
    prompt = _int_or_zero(body.get("prompt_tokens"))
    completion = _int_or_zero(body.get("completion_tokens"))
    details = body.get("completion_tokens_details")
    reasoning: int | None = None
    if isinstance(details, dict):
        raw = cast(dict[str, Any], details).get("reasoning_tokens")
        if isinstance(raw, int) and not isinstance(raw, bool):
            reasoning = raw
    return prompt, completion, reasoning


def _int_or_zero(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


class _UrllibMuseTransport:
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
            raise ModalMuseRequestError(
                f"Modal Muse chat completions returned HTTP {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ModalMuseRequestError(
                f"Modal Muse chat completions request failed: {exc.reason}"
            ) from exc
        if not isinstance(payload, bytes):
            raise ModalMuseRequestError("Modal Muse response body was not bytes")
        return payload


def _ledger_check(hook: object) -> Callable[[str], None] | None:
    check = getattr(hook, "check", None)
    if not callable(check):
        return None
    return cast(Callable[[str], None], check)


def _bind_before(hook: BeforeCall | _LedgerCheck | None) -> BeforeCall | None:
    if hook is None:
        return None
    check = _ledger_check(hook)
    if check is not None:
        return check
    if callable(hook):
        return hook
    raise TypeError("before_call must be a callable or a usage ledger")


def _bind_usage(hook: UsageHook | _LedgerCheck | None) -> UsageHook | None:
    if hook is None:
        return None
    if _ledger_check(hook) is not None:
        sink = cast(Callable[[_CreditUse], None], hook)

        def record(
            provider: str,
            model: str,
            input_tokens: int,
            output_tokens: int,
            reasoning_tokens: int | None,
        ) -> None:
            sink(
                _CreditUse(
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    reasoning_tokens,
                    time.time(),
                )
            )

        return record
    if callable(hook):
        return hook
    raise TypeError("on_usage must be a callable or a usage ledger")
