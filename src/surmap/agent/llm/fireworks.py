"""Fireworks chat models for the agent, through `langchain-openai`'s `ChatOpenAI`.

Fireworks serves the OpenAI chat completions dialect (`POST {base}/chat/completions`, OpenAI
`tools` / `tool_calls`, SSE streaming with `stream_options.include_usage`) at
`https://api.fireworks.ai/inference/v1`; `SURMAP_FIREWORKS_URL` overrides it. The stock client does
the wire mapping. `FireworksChatModel` adds only what SurMap needs around each call:

- the key (`FIREWORKS_API_KEY`) is required before any request and travels only in the
  `Authorization: Bearer` header; `ChatOpenAI` holds it as a `SecretStr`;
- `before_call("fireworks")` runs before every request and may raise (normally
  `UsageLedger.check`, so a spent `SURMAP_BUDGET_FIREWORKS_*` budget sends nothing);
- every response's token usage goes to `usage_sink` as a `UsageRecord` for provider `fireworks`;
- client failures become `FireworksError` naming only the exception type and the HTTP status —
  never the request, which holds the key. A 401 / 403 says to check `FIREWORKS_API_KEY`.

A base URL must be `https`, or `http` on loopback (a local stub), so the key never crosses a
network in clear text. `fireworks_models` lists the models a key can call: the comma-separated
override when given, else `GET {base}/models` (`data[].id`) through a small GET seam with a short
timeout, else `DEFAULT_FIREWORKS_MODELS`.
"""

from __future__ import annotations

import http.client
import json
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

import openai
from langchain_core.messages import BaseMessage, UsageMetadata
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import Field, SecretStr, SkipValidation

from surmap.labelling.meta_muse import BeforeCall
from surmap.usage import UsageRecord, UsageSink

__all__ = [
    "DEFAULT_FIREWORKS_MODELS",
    "DEFAULT_FIREWORKS_URL",
    "FIREWORKS_API_KEY_ENV",
    "FIREWORKS_MODELS_ENV",
    "FIREWORKS_PROVIDER",
    "FIREWORKS_URL_ENV",
    "FireworksChatModel",
    "FireworksError",
    "FireworksModelsTransport",
    "UrllibFireworksModelsTransport",
    "fireworks_base_url",
    "fireworks_chat_model",
    "fireworks_models",
]

FIREWORKS_PROVIDER = "fireworks"
"""The provider name usage is recorded under, and the registry id prefix."""
FIREWORKS_API_KEY_ENV = "FIREWORKS_API_KEY"
FIREWORKS_URL_ENV = "SURMAP_FIREWORKS_URL"
"""Overrides the Fireworks base URL (`https`, or `http` on loopback)."""
FIREWORKS_MODELS_ENV = "SURMAP_FIREWORKS_MODELS"
"""Comma-separated model ids to list instead of asking the endpoint."""
DEFAULT_FIREWORKS_URL = "https://api.fireworks.ai/inference/v1"
DEFAULT_FIREWORKS_MODELS: tuple[str, ...] = (
    "accounts/fireworks/models/llama-v3p3-70b-instruct",
    "accounts/fireworks/models/qwen3-235b-a22b",
    "accounts/fireworks/models/kimi-k2-instruct",
)
"""Tool-capable chat models listed when neither the override nor the endpoint names any."""
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_KEY_STATUSES = frozenset({401, 403})


class FireworksError(RuntimeError):
    """A Fireworks call could not be made or was refused. Never carries the key."""


class FireworksModelsTransport(Protocol):
    """One JSON GET. Raises `FireworksError` when the endpoint cannot be read."""

    def get_json(self, url: str, headers: Mapping[str, str]) -> Mapping[str, object]: ...


class UrllibFireworksModelsTransport:
    """Stdlib GET with a short timeout. `https`, or `http` on loopback; nothing else."""

    def __init__(self, timeout_s: float = 2.0) -> None:
        self._timeout_s = timeout_s

    def get_json(self, url: str, headers: Mapping[str, str]) -> Mapping[str, object]:
        parsed = urlsplit(fireworks_base_url(url))
        host = parsed.hostname or ""
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        connection: http.client.HTTPConnection
        if parsed.scheme == "https":
            connection = http.client.HTTPSConnection(
                host, parsed.port or 443, timeout=self._timeout_s
            )
        else:
            connection = http.client.HTTPConnection(
                host, parsed.port or 80, timeout=self._timeout_s
            )
        try:
            try:
                connection.request("GET", path, headers={"Accept": "application/json", **headers})
                response = connection.getresponse()
                raw = response.read()
                status = response.status
            finally:
                connection.close()
        except (OSError, http.client.HTTPException) as exc:
            raise FireworksError(f"Fireworks model listing failed: {type(exc).__name__}") from None
        if status != 200:
            raise FireworksError(f"Fireworks model listing returned HTTP {status}")
        try:
            decoded: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise FireworksError("Fireworks model listing was not JSON") from None
        if not isinstance(decoded, dict):
            raise FireworksError("Fireworks model listing was not a JSON object")
        return decoded


class FireworksChatModel(ChatOpenAI):
    """`ChatOpenAI` on Fireworks, with SurMap's budget gate, usage ledger and key-safe errors."""

    usage_sink: SkipValidation[UsageSink] | None = Field(default=None, exclude=True)
    """Receives one `UsageRecord` per response; normally a `UsageLedger`."""
    before_call: SkipValidation[BeforeCall] | None = Field(default=None, exclude=True)
    """Runs with `"fireworks"` before every request and may raise; normally `UsageLedger.check`."""

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._before_request()
        failure: FireworksError | None = None
        try:
            result = super()._generate(messages, stop, run_manager, **kwargs)
        except openai.OpenAIError as exc:
            failure = _redacted(exc)
        if failure is not None:
            raise failure
        self._record(_result_usage(result))
        return result

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._before_request()
        failure: FireworksError | None = None
        try:
            result = await super()._agenerate(messages, stop, run_manager, **kwargs)
        except openai.OpenAIError as exc:
            failure = _redacted(exc)
        if failure is not None:
            raise failure
        self._record(_result_usage(result))
        return result

    def _stream(self, *args: Any, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        self._before_request()
        usage: list[UsageMetadata] = []
        failure: FireworksError | None = None
        try:
            for chunk in super()._stream(*args, **kwargs):
                _collect(chunk, usage)
                yield chunk
        except openai.OpenAIError as exc:
            failure = _redacted(exc)
        if failure is not None:
            raise failure
        self._record(_summed(usage))

    async def _astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        self._before_request()
        usage: list[UsageMetadata] = []
        failure: FireworksError | None = None
        try:
            async for chunk in super()._astream(*args, **kwargs):
                _collect(chunk, usage)
                yield chunk
        except openai.OpenAIError as exc:
            failure = _redacted(exc)
        if failure is not None:
            raise failure
        self._record(_summed(usage))

    def _before_request(self) -> None:
        """Refuse a missing key, then let the budget gate refuse; nothing is sent either way."""
        key = self.openai_api_key
        if not isinstance(key, SecretStr) or not key.get_secret_value().strip():
            raise FireworksError(f"{FIREWORKS_API_KEY_ENV} is not set")
        if self.before_call is not None:
            self.before_call(FIREWORKS_PROVIDER)

    def _record(self, usage: UsageMetadata | None) -> None:
        if self.usage_sink is None or usage is None:
            return
        details = usage.get("output_token_details") or {}
        reasoning = details.get("reasoning")
        self.usage_sink(
            UsageRecord(
                provider=FIREWORKS_PROVIDER,
                model=self.model_name,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                reasoning_tokens=reasoning if isinstance(reasoning, int) else None,
                t_unix=time.time(),
            )
        )


def _redacted(exc: openai.OpenAIError) -> FireworksError:
    """A `FireworksError` naming only the exception type and status.

    Raised by the caller outside its `except` block, so neither `__cause__` nor `__context__`
    keeps the client exception, whose request holds the key.
    """
    name = type(exc).__name__
    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code
        if status in _KEY_STATUSES:
            return FireworksError(
                f"Fireworks refused the key: {name} (HTTP {status}); check {FIREWORKS_API_KEY_ENV}"
            )
        return FireworksError(f"Fireworks request failed: {name} (HTTP {status})")
    return FireworksError(f"Fireworks request failed: {name}")


def _collect(chunk: ChatGenerationChunk, usage: list[UsageMetadata]) -> None:
    metadata = getattr(chunk.message, "usage_metadata", None)
    if metadata is not None:
        usage.append(metadata)


def _summed(usage: list[UsageMetadata]) -> UsageMetadata | None:
    if not usage:
        return None
    input_tokens = sum(u["input_tokens"] for u in usage)
    output_tokens = sum(u["output_tokens"] for u in usage)
    return UsageMetadata(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def _result_usage(result: ChatResult) -> UsageMetadata | None:
    usage: list[UsageMetadata] = []
    for generation in result.generations:
        metadata = getattr(generation.message, "usage_metadata", None)
        if metadata is not None:
            usage.append(metadata)
    if len(usage) == 1:
        return usage[0]
    return _summed(usage)


def fireworks_base_url(explicit: str | None = None) -> str:
    """The base URL without a trailing slash; `FireworksError` unless `https` or loopback `http`.

    `explicit` blank or `None` is the public endpoint.
    """
    url = (explicit or "").strip().rstrip("/") or DEFAULT_FIREWORKS_URL
    parsed = urlsplit(url)
    host = parsed.hostname
    if host is None or not (
        parsed.scheme == "https" or (parsed.scheme == "http" and host in _LOOPBACK_HOSTS)
    ):
        raise FireworksError("Fireworks URL must be https (or http on loopback)")
    return url


def fireworks_chat_model(
    model: str,
    *,
    api_key: str,
    base_url: str | None = None,
    usage_sink: UsageSink | None = None,
    before_call: BeforeCall | None = None,
    max_retries: int = 2,
) -> FireworksChatModel:
    """A tool-bindable Fireworks model `model` (a path such as `accounts/fireworks/models/…`).

    Usage is requested on the streaming path too (`stream_usage`), and chat completions are always
    used — Fireworks has no Responses API.
    """
    return FireworksChatModel(
        model=model,
        base_url=fireworks_base_url(base_url),
        api_key=SecretStr(api_key),
        stream_usage=True,
        use_responses_api=False,
        max_retries=max_retries,
        usage_sink=usage_sink,
        before_call=before_call,
    )


def fireworks_models(
    transport: FireworksModelsTransport,
    *,
    api_key: str,
    base_url: str | None = None,
    override: str | None = None,
) -> tuple[str, ...]:
    """The override's ids, else the endpoint's `data[].id`, else `DEFAULT_FIREWORKS_MODELS`.

    The override is comma-separated, blank entries dropped. The endpoint is asked with the key as a
    bearer token; any failure (an unreachable endpoint, a refused key, a URL that is not `https` or
    loopback `http`), or an empty listing, falls back to the built-in list.
    """
    if override is not None and override.strip():
        return tuple(name.strip() for name in override.split(",") if name.strip())
    try:
        url = f"{fireworks_base_url(base_url)}/models"
        payload = transport.get_json(url, {"Authorization": f"Bearer {api_key}"})
    except FireworksError:
        return DEFAULT_FIREWORKS_MODELS
    data = payload.get("data")
    names: list[str] = []
    if isinstance(data, list):
        for entry in data:
            name = entry.get("id") if isinstance(entry, Mapping) else None
            if isinstance(name, str) and name:
                names.append(name)
    return tuple(names) or DEFAULT_FIREWORKS_MODELS
