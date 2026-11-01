"""One civilian scene note per call, from hosted Muse Spark.

The station posts a mapped JPEG and the on-board labels to the Meta
Model API Responses endpoint and reads back a search-and-rescue
description. The prompt asks for no flight advice. The default model
is hosted Muse Spark. ``SURMAP_META_MODEL`` or the constructor may
select another covered id, including Muse Wonder. Muse Wonder Full
and the Baseten slug ``meta-models/muse-spark-open-1026`` are refused.

The live request shape was checked on 2026-10-28: ``POST
https://api.meta.ai/v1/responses`` with ``Authorization: Bearer
$MODEL_API_KEY``. ``reasoning.effort`` defaults to ``high``. A
constructor argument wins over ``SURMAP_META_REASONING_EFFORT``,
which must be ``low``, ``medium``, or ``high``. ``max_output_tokens``
defaults to 4096 (visible output plus reasoning) and
``SURMAP_META_MAX_OUTPUT_TOKENS`` overrides that when the constructor
omits a cap. Image input follows Meta's image-understanding guide:
an ``input_image`` part whose ``image_url`` is a ``data:`` URL string.

The key is read from ``MODEL_API_KEY`` (or the constructor) at call
time. It is not written into the body, the error text, or ``repr``.
``before_call("meta")`` runs after the request is built and may raise
to block it. ``on_usage`` then receives
``("meta", model, input_tokens, output_tokens, reasoning_tokens)``
from the response ``usage`` object.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from surmap.labelling.baseten_muse import ObjectLabel
from surmap.types import Vec3

HOSTED_MUSE_SPARK_MODEL = "muse-spark-1.3"
META_MODEL_API_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_MAX_OUTPUT_TOKENS = 4096
_MIN_OUTPUT_TOKENS = 16
_REASONING_EFFORTS = frozenset({"low", "medium", "high"})
_REASONING_ENV = "SURMAP_META_REASONING_EFFORT"
_MAX_OUTPUT_ENV = "SURMAP_META_MAX_OUTPUT_TOKENS"
_MODEL_ENV = "SURMAP_META_MODEL"

BeforeCall = Callable[[str], None]
OnUsage = Callable[[str, str, int, int, int | None], None]

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
        model: str | None = None,
        reasoning_effort: str | None = None,
        base_url: str = META_MODEL_API_BASE_URL,
        timeout_s: float = 60.0,
        before_call: BeforeCall | None = None,
        on_usage: OnUsage | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self._model = _resolve_model(model)
        self._reasoning_effort = _resolve_reasoning_effort(reasoning_effort)
        self._max_output_tokens = _resolve_max_output_tokens(max_output_tokens)
        self._url = _responses_url(base_url)
        self._api_key = api_key
        self._before_call = before_call
        self._on_usage = on_usage
        self._transport = (
            transport if transport is not None else UrllibMetaMuseTransport(timeout_s=timeout_s)
        )

    @property
    def model(self) -> str:
        return self._model

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
            max_output_tokens=self._max_output_tokens,
        )
        headers = {
            "Authorization": f"Bearer {self._bearer_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._before_call is not None:
            self._before_call("meta")
        payload = self._transport.post_json(self._url, headers, body)
        _notify_usage(payload, self._model, self._on_usage)
        return _scene_note_text(payload)

    def __repr__(self) -> str:
        return (
            f"MetaMuseSceneClient(model={self._model!r}, "
            f"reasoning_effort={self._reasoning_effort!r}, "
            f"max_output_tokens={self._max_output_tokens})"
        )

    def _bearer_key(self) -> str:
        key = self._api_key if self._api_key is not None else os.environ.get("MODEL_API_KEY", "")
        stripped = key.strip()
        if not stripped:
            raise MetaMuseSceneError("MODEL_API_KEY is not set")
        return stripped


class MetaMuseLabelClient:
    """One noun phrase per crop, from hosted Muse Spark on the Meta Model API.

    Same Responses endpoint and bearer key as ``MetaMuseSceneClient``.
    The map point is not sent. Tests pass a transport and do not open a socket.
    """

    def __init__(
        self,
        *,
        transport: MetaMuseTransport | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = META_MODEL_API_BASE_URL,
        timeout_s: float = 60.0,
        before_call: BeforeCall | None = None,
        on_usage: OnUsage | None = None,
    ) -> None:
        self._model = _resolve_model(model)
        self._url = _responses_url(base_url)
        self._api_key = api_key
        self._before_call = before_call
        self._on_usage = on_usage
        self._transport = (
            transport if transport is not None else UrllibMetaMuseTransport(timeout_s=timeout_s)
        )

    @property
    def model(self) -> str:
        return self._model

    def label(self, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel:
        """Label one JPEG crop. ``xyz`` is attached after the reply."""
        if not jpeg.startswith(b"\xff\xd8"):
            raise MetaMuseSceneError("label crop must be a JPEG")
        encoded = base64.b64encode(jpeg).decode("ascii")
        body = _request_body(
            model=self._model,
            prompt=_label_prompt(coarse_label),
            image_url=f"data:image/jpeg;base64,{encoded}",
            reasoning_effort=DEFAULT_REASONING_EFFORT,
            max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        )
        headers = {
            "Authorization": f"Bearer {self._bearer_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._before_call is not None:
            self._before_call("meta")
        payload = self._transport.post_json(self._url, headers, body)
        _notify_usage(payload, self._model, self._on_usage)
        text = _scene_note_text(payload)
        phrase = text.splitlines()[0].strip()
        return ObjectLabel(
            label=phrase[:80],
            description=text,
            confidence=None,
            model_id=self._model,
            raw_text=text,
            map_point=xyz,
        )

    def _bearer_key(self) -> str:
        key = self._api_key if self._api_key is not None else os.environ.get("MODEL_API_KEY", "")
        stripped = key.strip()
        if not stripped:
            raise MetaMuseSceneError("MODEL_API_KEY is not set")
        return stripped


def _label_prompt(coarse_label: str) -> str:
    hint = " ".join(coarse_label.split()) or "object"
    return (
        "You label one photo crop for a civilian disaster-response map. "
        f"The segmenter noun was {hint}. Reply with one short noun phrase "
        "for what is visible, such as debris, vehicle, roof, or person. "
        "Do not give flight advice."
    )


def _resolve_model(explicit: str | None) -> str:
    if explicit is not None:
        return _check_model(explicit)
    raw = os.environ.get(_MODEL_ENV, "").strip()
    if not raw:
        return _check_model(HOSTED_MUSE_SPARK_MODEL)
    return _check_model(raw)


def _check_model(model: str) -> str:
    cleaned = model.strip()
    if not cleaned:
        raise MetaMuseSceneError("model id is empty")
    folded = cleaned.casefold().replace("_", "-").replace(" ", "-")
    if "wonder-full" in folded:
        raise MetaMuseSceneError("Muse Wonder Full is not covered by these credits")
    if folded == _OPEN_WEIGHT_ID or cleaned.casefold().startswith("meta-models/"):
        raise MetaMuseSceneError("Muse Spark Open is called on Baseten, not the Meta Model API")
    return cleaned


def _resolve_reasoning_effort(explicit: str | None) -> str:
    if explicit is not None:
        return _check_effort(explicit)
    return _check_effort(os.environ.get(_REASONING_ENV, DEFAULT_REASONING_EFFORT))


def _check_effort(effort: str) -> str:
    cleaned = effort.strip().casefold()
    if cleaned not in _REASONING_EFFORTS:
        raise MetaMuseSceneError("reasoning effort must be low, medium, or high")
    return cleaned


def _resolve_max_output_tokens(explicit: int | None) -> int:
    if explicit is not None:
        return _check_max_output_tokens(explicit)
    raw = os.environ.get(_MAX_OUTPUT_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_MAX_OUTPUT_TOKENS
    try:
        parsed = int(raw.strip())
    except ValueError as exc:
        raise MetaMuseSceneError(
            "SURMAP_META_MAX_OUTPUT_TOKENS must be an integer of at least 16"
        ) from exc
    return _check_max_output_tokens(parsed)


def _check_max_output_tokens(value: int) -> int:
    if isinstance(value, bool) or value < _MIN_OUTPUT_TOKENS:
        raise MetaMuseSceneError("max_output_tokens must be at least 16")
    return value


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
    max_output_tokens: int,
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
        "max_output_tokens": max_output_tokens,
    }


def _notify_usage(payload: Mapping[str, object], model: str, on_usage: OnUsage | None) -> None:
    if on_usage is None:
        return
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return
    input_tokens = _token_count(usage.get("input_tokens"))
    output_tokens = _token_count(usage.get("output_tokens"))
    if input_tokens is None or output_tokens is None:
        return
    on_usage("meta", model, input_tokens, output_tokens, _reasoning_tokens(usage))


def _reasoning_tokens(usage: Mapping[str, object]) -> int | None:
    details = usage.get("output_tokens_details")
    if not isinstance(details, dict):
        return None
    return _token_count(details.get("reasoning_tokens"))


def _token_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


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
