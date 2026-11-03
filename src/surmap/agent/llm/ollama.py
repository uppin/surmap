"""Local Ollama chat models for the agent, through `langchain-ollama`'s `ChatOllama`.

The server is the loopback Ollama API the labelling clients already use (`SURMAP_OLLAMA_URL`
overrides `http://127.0.0.1:11434`); no key exists or is sent. `ollama_models` asks
`GET /api/tags` which models the server holds. `OllamaTransport` in `surmap.labelling.ollama` is a
POST-only seam, so the tag listing has its own one-method GET protocol beside it; tests substitute
a fake and nothing here opens a socket under test.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from langchain_ollama import ChatOllama

__all__ = [
    "OllamaTagsTransport",
    "UrllibOllamaTagsTransport",
    "ollama_base_url",
    "ollama_chat_model",
    "ollama_models",
]


class OllamaTagsTransport(Protocol):
    """One JSON GET to the Ollama API. Raises `OllamaError` when the server cannot be reached."""

    def get_json(self, url: str) -> Mapping[str, object]: ...


class UrllibOllamaTagsTransport:
    """Stdlib GET. Loopback `http` or any `https`; nothing else."""

    def __init__(self, timeout_s: float = 2.0) -> None:
        self._timeout_s = timeout_s

    def get_json(self, url: str) -> Mapping[str, object]:
        raise NotImplementedError  # TODO(pr-5): implement


def ollama_base_url(explicit: str | None = None) -> str:
    """The Ollama base URL: explicit, else `SURMAP_OLLAMA_URL`, else the loopback default."""
    raise NotImplementedError  # TODO(pr-5): implement


def ollama_chat_model(name: str, *, base_url: str | None = None) -> ChatOllama:
    """A tool-bindable `ChatOllama` for model `name` on the configured server."""
    raise NotImplementedError  # TODO(pr-5): implement


def ollama_models(
    transport: OllamaTagsTransport, *, base_url: str | None = None
) -> tuple[str, ...]:
    """The model names `GET /api/tags` lists, in server order; `()` when the server is silent."""
    raise NotImplementedError  # TODO(pr-5): implement
