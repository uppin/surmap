"""Local Ollama chat models for the agent, through `langchain-ollama`'s `ChatOllama`.

The server is the loopback Ollama API the labelling clients already use (`SURMAP_OLLAMA_URL`
overrides `http://127.0.0.1:11434`); no key exists or is sent. `ollama_models` asks
`GET /api/tags` which models the server holds. `OllamaTransport` in `surmap.labelling.ollama` is a
POST-only seam, so the tag listing has its own one-method GET protocol beside it; tests substitute
a fake and nothing here opens a socket under test.
"""

from __future__ import annotations

import http.client
import json
import os
from collections.abc import Mapping
from typing import Protocol
from urllib.parse import urlsplit

from langchain_ollama import ChatOllama

from surmap.labelling.ollama import DEFAULT_OLLAMA_URL, OllamaError

__all__ = [
    "OLLAMA_URL_ENV",
    "OllamaTagsTransport",
    "UrllibOllamaTagsTransport",
    "ollama_base_url",
    "ollama_chat_model",
    "ollama_models",
]

OLLAMA_URL_ENV = "SURMAP_OLLAMA_URL"
"""Overrides the Ollama server; the same variable the labelling clients read."""
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class OllamaTagsTransport(Protocol):
    """One JSON GET to the Ollama API. Raises `OllamaError` when the server cannot be reached."""

    def get_json(self, url: str) -> Mapping[str, object]: ...


class UrllibOllamaTagsTransport:
    """Stdlib GET. Loopback `http` or any `https`; nothing else."""

    def __init__(self, timeout_s: float = 2.0) -> None:
        self._timeout_s = timeout_s

    def get_json(self, url: str) -> Mapping[str, object]:
        parsed = urlsplit(url)
        host = parsed.hostname
        if host is None or not (
            parsed.scheme == "https" or (parsed.scheme == "http" and host in _LOOPBACK_HOSTS)
        ):
            raise OllamaError("Ollama URL must be loopback http or https")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        try:
            connection: http.client.HTTPConnection
            if parsed.scheme == "https":
                connection = http.client.HTTPSConnection(
                    host, parsed.port or 443, timeout=self._timeout_s
                )
            else:
                connection = http.client.HTTPConnection(
                    host, parsed.port or 11434, timeout=self._timeout_s
                )
            try:
                connection.request("GET", path, headers={"Accept": "application/json"})
                response = connection.getresponse()
                raw = response.read()
                status = response.status
            finally:
                connection.close()
        except (OSError, http.client.HTTPException) as exc:
            raise OllamaError(
                "Ollama request failed — is `ollama serve` running on this machine?"
            ) from exc
        if status != 200:
            raise OllamaError(f"Ollama returned HTTP {status}")
        return _json_object(raw)


def ollama_base_url(explicit: str | None = None) -> str:
    """The Ollama base URL: explicit, else `SURMAP_OLLAMA_URL`, else the loopback default."""
    for candidate in (explicit, os.environ.get(OLLAMA_URL_ENV)):
        if candidate is not None and candidate.strip():
            return candidate.strip().rstrip("/")
    return DEFAULT_OLLAMA_URL


def ollama_chat_model(name: str, *, base_url: str | None = None) -> ChatOllama:
    """A tool-bindable `ChatOllama` for model `name` on the configured server."""
    return ChatOllama(model=name, base_url=ollama_base_url(base_url))


def ollama_models(
    transport: OllamaTagsTransport, *, base_url: str | None = None
) -> tuple[str, ...]:
    """The model names `GET /api/tags` lists, in server order; `()` when the server is silent."""
    try:
        payload = transport.get_json(f"{ollama_base_url(base_url)}/api/tags")
    except OllamaError:
        return ()
    models = payload.get("models")
    if not isinstance(models, list):
        return ()
    names: list[str] = []
    for entry in models:
        name = entry.get("name") if isinstance(entry, Mapping) else None
        if isinstance(name, str):
            names.append(name)
    return tuple(names)


def _json_object(raw: bytes) -> dict[str, object]:
    try:
        decoded: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OllamaError("Ollama response was not JSON") from exc
    if not isinstance(decoded, dict):
        raise OllamaError("Ollama response was not a JSON object")
    return decoded
