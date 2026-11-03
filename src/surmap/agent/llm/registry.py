"""Which chat models the agent can use right now, and building one by id.

An id is `<provider>:<model>`, split at the first colon (`ollama:llama3.2:3b` is Ollama model
`llama3.2:3b`):

- `meta:<model>` is listed only when `MODEL_API_KEY` is set; the model is
  `SURMAP_AGENT_META_MODEL`, else `muse-wonder-1.0`.
- `ollama:<model>` is listed for every model the loopback server's `GET /api/tags` returns, and
  for none when the server does not answer.

`build` does not consult the listing: any `meta:` or `ollama:` id builds, and any other provider is
refused by name.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from surmap.agent.llm.fireworks import FireworksModelsTransport
from surmap.agent.llm.meta import (
    AGENT_META_MODEL_ENV,
    DEFAULT_AGENT_META_MODEL,
    META_PROVIDER,
    MetaResponsesChatModel,
)
from surmap.agent.llm.ollama import (
    OLLAMA_URL_ENV,
    OllamaTagsTransport,
    UrllibOllamaTagsTransport,
    ollama_base_url,
    ollama_chat_model,
    ollama_models,
)
from surmap.labelling.meta_muse import MetaMuseTransport
from surmap.labelling.ollama import DEFAULT_OLLAMA_URL
from surmap.usage import UsageSink

__all__ = ["ChatModelRegistry", "ModelInfo", "Provider", "UnknownModelProvider"]

Provider = Literal["meta", "fireworks", "ollama"]

_MODEL_API_KEY_ENV = "MODEL_API_KEY"


class UnknownModelProvider(ValueError):
    """A model id names a provider the registry does not build."""


@dataclass(frozen=True)
class ModelInfo:
    """One chat model the agent can run."""

    id: str
    """`<provider>:<model>`, what `ChatModelRegistry.build` takes."""
    provider: Provider
    model: str
    """The provider's own model name."""


class ChatModelRegistry:
    """Lists the configured, reachable chat models and builds one by id."""

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        ollama_transport: OllamaTagsTransport | None = None,
        meta_transport: MetaMuseTransport | None = None,
        fireworks_transport: FireworksModelsTransport | None = None,
        usage_sink: UsageSink | None = None,
    ) -> None:
        """`environ` defaults to `os.environ`; the transports to the stdlib ones.

        `meta_transport` and `usage_sink` are handed to every Muse model `build` returns.
        """
        self._environ = environ
        self._ollama_transport = ollama_transport
        self._meta_transport = meta_transport
        self._fireworks_transport = fireworks_transport
        self._usage_sink = usage_sink

    def available(self) -> tuple[ModelInfo, ...]:
        """Muse first (when keyed), then the Ollama server's models in its order."""
        environ = self._env()
        listed: list[ModelInfo] = []
        if environ.get(_MODEL_API_KEY_ENV, "").strip():
            muse = environ.get(AGENT_META_MODEL_ENV, "").strip() or DEFAULT_AGENT_META_MODEL
            listed.append(ModelInfo(id=f"{META_PROVIDER}:{muse}", provider="meta", model=muse))
        tags = (
            self._ollama_transport
            if self._ollama_transport is not None
            else UrllibOllamaTagsTransport()
        )
        for name in ollama_models(tags, base_url=self._ollama_url()):
            listed.append(ModelInfo(id=f"ollama:{name}", provider="ollama", model=name))
        return tuple(listed)

    def build(self, model_id: str) -> BaseChatModel:
        """The chat model for `model_id`; `UnknownModelProvider` for any other provider."""
        provider, _, model = model_id.partition(":")
        if provider == META_PROVIDER and model:
            return MetaResponsesChatModel(
                model=model,
                api_key=SecretStr(self._env().get(_MODEL_API_KEY_ENV, "")),
                transport=self._meta_transport,
                usage_sink=self._usage_sink,
            )
        if provider == "ollama" and model:
            return ollama_chat_model(model, base_url=self._ollama_url())
        raise UnknownModelProvider(
            f"unknown model provider {provider!r} in {model_id!r}; "
            "the agent builds meta:<model> and ollama:<model> ids"
        )

    def _env(self) -> Mapping[str, str]:
        return os.environ if self._environ is None else self._environ

    def _ollama_url(self) -> str:
        # Read from the injected environment, never os.environ: the default is passed explicitly
        # so ollama_base_url does not fall back to the process environment.
        return ollama_base_url(self._env().get(OLLAMA_URL_ENV) or DEFAULT_OLLAMA_URL)
