"""Local labelling and scene notes from an Ollama-served model.

A fully local alternative to the hosted Meta Model API clients, behind
the same ports: ``OllamaLabelClient`` satisfies the ``LabelClient``
protocol and ``OllamaSceneClient`` the scene-note shape the mission
uses. The model is the operator's choice — any vision model Ollama
serves — named by ``--ollama-model`` or ``SURMAP_OLLAMA_MODEL``; the
server is expected on the loopback Ollama API (``SURMAP_OLLAMA_URL``
overrides the base URL).
No key exists or is sent. Tests substitute a recording transport, so
nothing here opens a socket under test.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
from collections.abc import Mapping, Sequence
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from surmap.labelling.baseten_muse import ObjectLabel
from surmap.types import Vec3

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
_URL_ENV = "SURMAP_OLLAMA_URL"
_MODEL_ENV = "SURMAP_OLLAMA_MODEL"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class OllamaError(RuntimeError):
    """The local Ollama model could not be reached or read."""


class OllamaTransport(Protocol):
    """One JSON POST to the Ollama API. Tests substitute a fake."""

    def post_json(self, url: str, body: Mapping[str, object]) -> Mapping[str, object]: ...


class UrllibOllamaTransport:
    """Stdlib POST. Loopback `http` or any `https`; nothing else."""

    def __init__(self, timeout_s: float = 300.0) -> None:
        if timeout_s <= 0:
            raise OllamaError("timeout must be positive")
        self._timeout_s = timeout_s

    def post_json(self, url: str, body: Mapping[str, object]) -> Mapping[str, object]:
        parsed = urlsplit(url)
        host = parsed.hostname
        if host is None or not (
            parsed.scheme == "https" or (parsed.scheme == "http" and host in _LOOPBACK_HOSTS)
        ):
            raise OllamaError("Ollama URL must be loopback http or https")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        payload = json.dumps(body).encode("utf-8")
        try:
            if parsed.scheme == "https":
                connection: http.client.HTTPConnection = http.client.HTTPSConnection(
                    host, parsed.port or 443, timeout=self._timeout_s
                )
            else:
                connection = http.client.HTTPConnection(
                    host, parsed.port or 11434, timeout=self._timeout_s
                )
            try:
                connection.request(
                    "POST",
                    path,
                    body=payload,
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                )
                response = connection.getresponse()
                raw = response.read()
                status = response.status
            finally:
                connection.close()
        except OllamaError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise OllamaError(
                "Ollama request failed — is `ollama serve` running on this machine?"
            ) from exc
        if status != 200:
            raise OllamaError(f"Ollama returned HTTP {status}")
        return _parse_json_object(raw)


def ollama_model(explicit: str | None = None) -> str:
    """The operator-chosen model: explicit, else `SURMAP_OLLAMA_MODEL`.

    Any vision model in `ollama list` qualifies. There is deliberately
    no built-in model name: an unconfigured run fails here and names
    the option instead of silently picking a model for the operator.
    """
    if explicit is not None and explicit.strip():
        return explicit.strip()
    configured = os.environ.get(_MODEL_ENV, "").strip()
    if configured:
        return configured
    raise OllamaError(
        "no Ollama model configured: pass --ollama-model or set "
        "SURMAP_OLLAMA_MODEL to any vision model from `ollama list`"
    )


def ollama_chat_url(base_url: str | None = None) -> str:
    """The `/api/chat` endpoint for the configured Ollama base URL."""
    raw = (base_url or os.environ.get(_URL_ENV, "") or DEFAULT_OLLAMA_URL).strip()
    parsed = urlsplit(raw)
    if parsed.hostname is None:
        raise OllamaError("Ollama URL must name a host")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, f"{path}/api/chat", "", ""))


def chat_content(payload: Mapping[str, object]) -> str:
    """The assistant text of an Ollama chat reply, or a named failure."""
    message = payload.get("message")
    if not isinstance(message, Mapping):
        raise OllamaError("Ollama response had no message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaError("Ollama response had no text")
    return content.strip()


def chat_body(model: str, prompt: str, image: bytes) -> dict[str, object]:
    """One non-streaming vision chat request with a base64 image."""
    return {
        "model": model,
        "stream": False,
        "options": {"temperature": 0},
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64.b64encode(image).decode("ascii")],
            }
        ],
    }


class OllamaLabelClient:
    """One noun phrase per crop, from the local model. Satisfies `LabelClient`."""

    def __init__(
        self,
        *,
        model: str | None = None,
        transport: OllamaTransport | None = None,
        base_url: str | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        self._model = ollama_model(model)
        self._url = ollama_chat_url(base_url)
        self._transport = (
            transport if transport is not None else UrllibOllamaTransport(timeout_s=timeout_s)
        )

    @property
    def model(self) -> str:
        return f"ollama:{self._model}"

    def label(self, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel:
        """Label one image crop. ``xyz`` is attached after the reply."""
        if not jpeg:
            raise OllamaError("label crop is empty")
        payload = self._transport.post_json(
            self._url, chat_body(self._model, _label_prompt(coarse_label), jpeg)
        )
        text = chat_content(payload)
        phrase = text.splitlines()[0].strip()
        return ObjectLabel(
            label=phrase[:80],
            description=text,
            confidence=None,
            model_id=self.model,
            raw_text=text,
            map_point=xyz,
        )


class OllamaSceneClient:
    """One civilian scene note per call, from the local model."""

    def __init__(
        self,
        *,
        model: str | None = None,
        transport: OllamaTransport | None = None,
        base_url: str | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        self._model = ollama_model(model)
        self._url = ollama_chat_url(base_url)
        self._transport = (
            transport if transport is not None else UrllibOllamaTransport(timeout_s=timeout_s)
        )

    @property
    def model(self) -> str:
        return f"ollama:{self._model}"

    def note(self, labels: Sequence[str], frame_jpeg: bytes) -> str:
        """Describe the mapped area. ``labels`` are the recorded object labels."""
        if not frame_jpeg:
            raise OllamaError("scene note frame is empty")
        payload = self._transport.post_json(
            self._url, chat_body(self._model, _scene_prompt(labels), frame_jpeg)
        )
        return chat_content(payload)


def _label_prompt(coarse_label: str) -> str:
    hint = " ".join(coarse_label.split()) or "object"
    return (
        "You label one photo crop for a civilian disaster-response map. "
        f"The segmenter noun was {hint}. Reply with one short noun phrase "
        "for what is visible, such as debris, vehicle, roof, or person. "
        "Do not give flight advice."
    )


def _scene_prompt(labels: Sequence[str]) -> str:
    cleaned = [" ".join(label.split()) for label in labels if label.strip()]
    context = (
        "Recorded object labels: " + ", ".join(cleaned) + "."
        if cleaned
        else "No object labels were recorded."
    )
    return (
        "Write one civilian search-and-rescue scene note for a disaster-response "
        "team looking at a mapped area. Describe landmarks, debris, and vehicles "
        f"visible in the image. {context} Do not give flight advice, navigation, "
        "or any instruction to an aircraft."
    )


def _parse_json_object(raw: bytes) -> dict[str, object]:
    try:
        decoded: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OllamaError("Ollama response was not JSON") from exc
    if not isinstance(decoded, dict):
        raise OllamaError("Ollama response was not a JSON object")
    parsed: dict[str, object] = {}
    for key, item in decoded.items():
        if not isinstance(key, str):
            raise OllamaError("Ollama response had a non-text field name")
        parsed[key] = item
    return parsed
