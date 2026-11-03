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

from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any, Protocol

from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import Field, SkipValidation

from surmap.labelling.meta_muse import BeforeCall
from surmap.usage import UsageSink

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
        raise NotImplementedError  # red stub


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
        raise NotImplementedError  # red stub

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError  # red stub

    def _stream(self, *args: Any, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        raise NotImplementedError  # red stub

    def _astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        raise NotImplementedError  # red stub


def fireworks_base_url(explicit: str | None = None) -> str:
    """The base URL without a trailing slash; `FireworksError` unless `https` or loopback `http`."""
    raise NotImplementedError  # red stub


def fireworks_chat_model(
    model: str,
    *,
    api_key: str,
    base_url: str | None = None,
    usage_sink: UsageSink | None = None,
    before_call: BeforeCall | None = None,
    max_retries: int = 2,
) -> FireworksChatModel:
    """A tool-bindable Fireworks model `model` (a path such as `accounts/fireworks/models/…`)."""
    raise NotImplementedError  # red stub


def fireworks_models(
    transport: FireworksModelsTransport,
    *,
    api_key: str,
    base_url: str,
    override: str | None = None,
) -> tuple[str, ...]:
    """The override's ids, else the endpoint's `data[].id`, else `DEFAULT_FIREWORKS_MODELS`."""
    raise NotImplementedError  # red stub
