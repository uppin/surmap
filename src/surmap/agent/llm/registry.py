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

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

from surmap.agent.llm.ollama import OllamaTagsTransport
from surmap.labelling.meta_muse import MetaMuseTransport
from surmap.usage import UsageSink

__all__ = ["ChatModelRegistry", "ModelInfo", "Provider", "UnknownModelProvider"]

Provider = Literal["meta", "ollama"]


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
        usage_sink: UsageSink | None = None,
    ) -> None:
        """`environ` defaults to `os.environ`; the transports to the stdlib ones.

        `meta_transport` and `usage_sink` are handed to every Muse model `build` returns.
        """
        self._environ = environ
        self._ollama_transport = ollama_transport
        self._meta_transport = meta_transport
        self._usage_sink = usage_sink

    def available(self) -> tuple[ModelInfo, ...]:
        """Muse first (when keyed), then the Ollama server's models in its order."""
        raise NotImplementedError  # TODO(pr-5): implement

    def build(self, model_id: str) -> BaseChatModel:
        """The chat model for `model_id`; `UnknownModelProvider` for any other provider."""
        raise NotImplementedError  # TODO(pr-5): implement
