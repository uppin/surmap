"""One civilian scene note per call, from hosted Muse Spark.

The station posts a mapped JPEG and the on-board labels to the Meta
Model API Responses endpoint and reads back a search-and-rescue
description. The prompt asks for no flight advice. Muse Wonder is not
used, and the open-weight Muse Spark slug belongs on Baseten, not here.

The live request shape was checked on 2026-10-28: ``POST
https://api.meta.ai/v1/responses`` with ``Authorization: Bearer
$MODEL_API_KEY``. The API's default ``reasoning.effort`` is ``high``;
this client sends ``low`` unless the caller picks another effort.
Image input follows Meta's image-understanding guide: an
``input_image`` part whose ``image_url`` is a ``data:`` URL string.

The key is read from ``MODEL_API_KEY`` (or the constructor) at call
time. It is not written into the body, the error text, or ``repr``.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
from collections.abc import Mapping, Sequence
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

HOSTED_MUSE_SPARK_MODEL = "muse-spark-1.3"
META_MODEL_API_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_REASONING_EFFORT = "low"

_WONDER_ID = "muse-wonder"
_OPEN_WEIGHT_ID = "meta-models/muse-spark-open-1026"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


class MetaMuseSceneError(RuntimeError):
    """The scene note could not be requested or read."""


class MetaMuseTransport(Protocol):
    """One JSON POST. Tests substitute a recording fake."""

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object],
    ) -> Mapping[str, object]: ...


class UrllibMetaMuseTransport:
    """Stdlib POST that does not follow redirects.

    A redirect would be a second request, and the bearer token must
    stay on the call to the Meta host. Loopback ``http`` exists so
    tests can stand up a local server; every other URL must be https.
    """

    def __init__(self, timeout_s: float = 60.0) -> None:
        if timeout_s <= 0:
            raise MetaMuseSceneError("timeout must be positive")
        self._timeout_s = timeout_s

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object],
    ) -> Mapping[str, object]:
        parsed = urlsplit(url)
        host = parsed.hostname
        if host is None:
            raise MetaMuseSceneError("Meta Model API URL must be https")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        payload = json.dumps(body).encode("utf-8")
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **dict(headers),
        }
        try:
            connection = _open_connection(parsed.scheme, host, parsed.port, self._timeout_s)
            try:
                connection.request("POST", path, body=payload, headers=request_headers)
                response = connection.getresponse()
                raw = response.read()
                status = response.status
            finally:
                connection.close()
        except MetaMuseSceneError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise MetaMuseSceneError("Meta Model API request failed") from exc
        if status != 200:
            raise MetaMuseSceneError(f"Meta Model API returned HTTP {status}")
        return _parse_json_object(raw)


class MetaMuseSceneClient:
    """Posts one mapped frame and returns the assistant scene note."""

    def __init__(
        self,
        *,
        transport: MetaMuseTransport | None = None,
        api_key: str | None = None,
        model: str = HOSTED_MUSE_SPARK_MODEL,
        reasoning_effort: str = DEFAULT_REASONING_EFFORT,
        base_url: str = META_MODEL_API_BASE_URL,
        timeout_s: float = 60.0,
    ) -> None:
        self._model = _check_model(model)
        self._reasoning_effort = _check_effort(reasoning_effort)
        self._url = _responses_url(base_url)
        self._api_key = api_key
        self._transport = (
            transport if transport is not None else UrllibMetaMuseTransport(timeout_s=timeout_s)
        )

    def note(self, labels: Sequence[str], frame_jpeg: bytes) -> str:
        """Describe the mapped area. ``labels`` are on-board detector names."""
        prompt = _prompt(labels)
        if not frame_jpeg.startswith(b"\xff\xd8"):
            raise MetaMuseSceneError("scene note frame must be a JPEG")
        encoded = base64.b64encode(frame_jpeg).decode("ascii")
        body = _request_body(
            model=self._model,
            prompt=prompt,
            image_url=f"data:image/jpeg;base64,{encoded}",
            reasoning_effort=self._reasoning_effort,
        )
        payload = self._transport.post_json(
            self._url,
            {
                "Authorization": f"Bearer {self._bearer_key()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body,
        )
        return _scene_note_text(payload)

    def __repr__(self) -> str:
        return (
            f"MetaMuseSceneClient(model={self._model!r}, "
            f"reasoning_effort={self._reasoning_effort!r})"
        )

    def _bearer_key(self) -> str:
        key = self._api_key if self._api_key is not None else os.environ.get("MODEL_API_KEY", "")
        stripped = key.strip()
        if not stripped:
            raise MetaMuseSceneError("MODEL_API_KEY is not set")
        return stripped


def _check_model(model: str) -> str:
    cleaned = model.strip()
    if not cleaned:
        raise MetaMuseSceneError("model id is empty")
    lowered = cleaned.casefold()
    if _WONDER_ID in lowered:
        raise MetaMuseSceneError(
            "Muse Wonder is not used for the scene note; the hosted model is muse-spark-1.3"
        )
    if lowered == _OPEN_WEIGHT_ID or lowered.startswith("meta-models/"):
        raise MetaMuseSceneError("Muse Spark Open is called on Baseten, not the Meta Model API")
    return cleaned


def _check_effort(effort: str) -> str:
    cleaned = effort.strip()
    if not cleaned:
        raise MetaMuseSceneError("reasoning effort is empty")
    return cleaned


def _responses_url(base_url: str) -> str:
    parsed = urlsplit(base_url.strip())
    if parsed.scheme != "https" or parsed.hostname is None:
        raise MetaMuseSceneError("Meta Model API base URL must be https")
    if parsed.username is not None or parsed.password is not None:
        raise MetaMuseSceneError("Meta Model API base URL must not carry credentials")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, f"{path}/responses", "", ""))


def _prompt(labels: Sequence[str]) -> str:
    if isinstance(labels, str):
        raise MetaMuseSceneError("scene-note labels must be a sequence of labels, not one string")
    cleaned = [_one_label(label) for label in labels]
    if cleaned:
        context = "On-board labels: " + ", ".join(cleaned) + "."
    else:
        context = "No on-board labels were recorded."
    return (
        "Write one civilian search-and-rescue scene note for a disaster-response "
        "team looking at a mapped area. Describe landmarks, debris, and vehicles "
        f"visible in the image. {context} Do not give flight advice, navigation, "
        "or any instruction to an aircraft."
    )


def _one_label(label: str) -> str:
    collapsed = " ".join(label.split())
    if not collapsed:
        raise MetaMuseSceneError("scene-note label is empty")
    return collapsed


def _request_body(
    *,
    model: str,
    prompt: str,
    image_url: str,
    reasoning_effort: str,
) -> dict[str, object]:
    content: list[object] = [
        {"type": "input_text", "text": prompt},
        {"type": "input_image", "image_url": image_url},
    ]
    message: dict[str, object] = {"type": "message", "role": "user", "content": content}
    return {
        "model": model,
        "input": [message],
        "stream": False,
        "reasoning": {"effort": reasoning_effort},
    }


def _scene_note_text(payload: Mapping[str, object]) -> str:
    output = payload.get("output")
    if not isinstance(output, list):
        raise MetaMuseSceneError("Meta Model API response had no output list")
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "output_text":
                continue
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
    note = "".join(parts).strip()
    if not note:
        raise MetaMuseSceneError("Meta Model API response had no scene-note text")
    return note


def _open_connection(
    scheme: str, host: str, port: int | None, timeout_s: float
) -> http.client.HTTPConnection:
    if scheme == "https":
        return http.client.HTTPSConnection(host, port or 443, timeout=timeout_s)
    if scheme == "http" and host in _LOOPBACK_HOSTS:
        return http.client.HTTPConnection(host, port or 80, timeout=timeout_s)
    raise MetaMuseSceneError("Meta Model API URL must be https")


def _parse_json_object(raw: bytes) -> dict[str, object]:
    try:
        decoded: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetaMuseSceneError("Meta Model API response was not JSON") from exc
    if not isinstance(decoded, dict):
        raise MetaMuseSceneError("Meta Model API response was not a JSON object")
    parsed: dict[str, object] = {}
    for key, item in decoded.items():
        if not isinstance(key, str):
            raise MetaMuseSceneError("Meta Model API response had a non-text field name")
        parsed[key] = item
    return parsed
