"""One civilian scene note per call, from Muse Wonder on the Meta Model API.

The station posts a mapped JPEG and the on-board labels to the Meta
Model API Responses endpoint and reads back a search-and-rescue
description. The prompt asks for no flight advice. The default model
is Muse Wonder (``muse-wonder-1.0``) for the scene note, per-object
labels, and SAM concepts. ``SURMAP_META_MODEL`` or the constructor may
select another covered id, such as hosted Muse Spark (``muse-spark-1.3``).
Muse Wonder Full and the Baseten slug ``meta-models/muse-spark-open-1026``
are refused.

The live request shape was checked on 2026-10-28: ``POST
https://api.meta.ai/v1/responses`` with ``Authorization: Bearer
$MODEL_API_KEY``. ``reasoning.effort`` defaults to ``high``. A
constructor argument wins over ``SURMAP_META_REASONING_EFFORT``,
which must be ``low``, ``medium``, or ``high``. ``max_output_tokens``
defaults to 8192 (visible output plus reasoning, sized for Muse Wonder) and
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

HOSTED_MUSE_WONDER_MODEL = "muse-wonder-1.0"
META_MODEL_API_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_MAX_OUTPUT_TOKENS = 8192
_MIN_OUTPUT_TOKENS = 16
_REASONING_EFFORTS = frozenset({"low", "medium", "high"})
_REASONING_ENV = "SURMAP_META_REASONING_EFFORT"
_MAX_OUTPUT_ENV = "SURMAP_META_MAX_OUTPUT_TOKENS"
_MODEL_ENV = "SURMAP_META_MODEL"
LABEL_REASONING_EFFORT = "low"
_LABEL_REASONING_ENV = "SURMAP_META_LABEL_REASONING_EFFORT"

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

    def note(
        self,
        labels: Sequence[str],
        frame_jpeg: bytes,
        *,
        object_summary: Sequence[str] = (),
    ) -> str:
        """Describe the mapped area. ``labels`` are on-board detector names.

        ``object_summary`` is one line per mapped object after 3D
        deduplication (for example ``"person, static, 2 frames"``). The
        reply is plain text with three headed sections; see
        ``SCENE_NOTE_SECTIONS``.
        """
        prompt = _prompt(labels, object_summary)
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
    """One noun phrase per crop, from Muse Wonder on the Meta Model API.

    Same Responses endpoint and bearer key as ``MetaMuseSceneClient``.
    The map point is not sent. Tests pass a transport and do not open a socket.

    A crop label is a direct-answer task, so ``reasoning.effort`` defaults
    to ``low`` (``SURMAP_META_LABEL_REASONING_EFFORT`` or the constructor
    overrides it). The scene note and Ask the map keep ``high``.
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
        reasoning_effort: str | None = None,
    ) -> None:
        self._model = _resolve_model(model)
        self._reasoning_effort = _check_effort(
            reasoning_effort
            if reasoning_effort is not None
            else os.environ.get(_LABEL_REASONING_ENV, LABEL_REASONING_EFFORT)
        )
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

    @property
    def reasoning_effort(self) -> str:
        return self._reasoning_effort

    def label(self, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel:
        """Label one JPEG crop. ``xyz`` is attached after the reply."""
        if not jpeg.startswith(b"\xff\xd8"):
            raise MetaMuseSceneError("label crop must be a JPEG")
        encoded = base64.b64encode(jpeg).decode("ascii")
        body = _request_body(
            model=self._model,
            prompt=_label_prompt(coarse_label),
            image_url=f"data:image/jpeg;base64,{encoded}",
            reasoning_effort=self._reasoning_effort,
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


CONCEPT_SCHEMA_NAME = "sam_concepts"
DEFAULT_MAX_CONCEPTS = 4
CONCEPT_REASONING_EFFORT = "low"
CONCEPT_MAX_OUTPUT_TOKENS = 2048
ALWAYS_SEGMENTED = "person"
_CONCEPT_MAX_WORDS = 4
_CONCEPT_MAX_CHARS = 40
_CONCEPT_BLOCKED_WORDS = frozenset(
    {"no", "not", "without", "left", "right", "above", "below", "near", "behind", "and", "or"}
)


def concept_text_format(max_concepts: int) -> dict[str, object]:
    """Responses API ``text.format``: a JSON object holding a list of noun phrases."""
    return {
        "type": "json_schema",
        "name": CONCEPT_SCHEMA_NAME,
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "concepts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        f"At most {max_concepts} short noun phrases SAM 3.1 should segment."
                    ),
                }
            },
            "required": ["concepts"],
            "additionalProperties": False,
        },
    }


class MetaMuseConceptClient:
    """Muse Wonder picks the concepts SAM 3.1 segments in one keyframe.

    Uses structured output on the Responses API (``text.format`` with a
    JSON schema; ``response_format`` is the Chat Completions field and
    is not sent here). Every returned phrase is checked again locally:
    SAM takes one short noun phrase per request, so lists, negation,
    and spatial words are dropped. ``person`` is always first, because
    finding people is the point of the survey.
    """

    def __init__(
        self,
        *,
        transport: MetaMuseTransport | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_concepts: int = DEFAULT_MAX_CONCEPTS,
        base_url: str = META_MODEL_API_BASE_URL,
        timeout_s: float = 60.0,
        before_call: BeforeCall | None = None,
        on_usage: OnUsage | None = None,
    ) -> None:
        if max_concepts < 1:
            raise MetaMuseSceneError("max_concepts must be at least 1")
        self._model = _resolve_model(model)
        self._max_concepts = max_concepts
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

    @property
    def max_concepts(self) -> int:
        return self._max_concepts

    def propose(self, frame_jpeg: bytes) -> tuple[str, ...]:
        """Concepts to segment, ``person`` first, at most ``max_concepts``."""
        if not frame_jpeg.startswith(b"\xff\xd8"):
            raise MetaMuseSceneError("concept frame must be a JPEG")
        encoded = base64.b64encode(frame_jpeg).decode("ascii")
        body = _request_body(
            model=self._model,
            prompt=_concept_prompt(self._max_concepts),
            image_url=f"data:image/jpeg;base64,{encoded}",
            reasoning_effort=CONCEPT_REASONING_EFFORT,
            max_output_tokens=CONCEPT_MAX_OUTPUT_TOKENS,
        )
        body["text"] = {"format": concept_text_format(self._max_concepts)}
        headers = {
            "Authorization": f"Bearer {_bearer(self._api_key)}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._before_call is not None:
            self._before_call("meta")
        payload = self._transport.post_json(self._url, headers, body)
        _notify_usage(payload, self._model, self._on_usage)
        return parse_concepts(_scene_note_text(payload), self._max_concepts)


def parse_concepts(text: str, max_concepts: int) -> tuple[str, ...]:
    """Validated concepts from the structured reply. ``person`` is always first."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MetaMuseSceneError("concept reply was not JSON") from exc
    raw = parsed.get("concepts") if isinstance(parsed, dict) else None
    if not isinstance(raw, list):
        raise MetaMuseSceneError("concept reply had no concepts list")
    chosen: list[str] = [ALWAYS_SEGMENTED]
    for item in raw:
        if not isinstance(item, str):
            continue
        concept = clean_concept(item)
        if concept and concept not in chosen:
            chosen.append(concept)
    return tuple(chosen[:max_concepts])


def clean_concept(text: str) -> str:
    """One short noun phrase SAM accepts, or an empty string."""
    words = text.strip().strip(".").lower().split()
    if not words or len(words) > _CONCEPT_MAX_WORDS:
        return ""
    phrase = " ".join(words)
    if len(phrase) > _CONCEPT_MAX_CHARS:
        return ""
    if any(word in _CONCEPT_BLOCKED_WORDS for word in words):
        return ""
    if not all(char.isalpha() or char in " -" for char in phrase):
        return ""
    return phrase


def _concept_prompt(max_concepts: int) -> str:
    return (
        "You help a civilian search-and-rescue team map a disaster area from a "
        "survey drone's camera. Look at this frame and list up to "
        f"{max_concepts} things a segmentation model should outline so responders "
        "can find people who need help, damage, and blocked access: for example "
        "person, collapsed building, debris pile, flooded road, vehicle. Each item "
        "must be one short noun phrase of at most four words, with no lists, no "
        "negation, and no positions. Return JSON only. Do not give flight advice."
    )


def _bearer(explicit: str | None) -> str:
    key = explicit if explicit is not None else os.environ.get("MODEL_API_KEY", "")
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
        return _check_model(HOSTED_MUSE_WONDER_MODEL)
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


SCENE_NOTE_SECTIONS = ("Immediate hazards", "Survivor locations", "Access and debris blockages")


def _prompt(labels: Sequence[str], object_summary: Sequence[str] = ()) -> str:
    if isinstance(labels, str):
        raise MetaMuseSceneError("scene-note labels must be a sequence of labels, not one string")
    if isinstance(object_summary, str):
        raise MetaMuseSceneError("object summary must be a sequence of lines, not one string")
    cleaned = [_one_label(label) for label in labels]
    if cleaned:
        context = "On-board labels: " + ", ".join(cleaned) + "."
    else:
        context = "No on-board labels were recorded."
    summary = [" ".join(line.split()) for line in object_summary if line.strip()]
    if summary:
        context += " Mapped objects, one line each after 3D deduplication:\n" + "\n".join(
            f"- {line}" for line in summary
        )
    sections = ", ".join(f'"{name}"' for name in SCENE_NOTE_SECTIONS)
    return (
        "Write one civilian search-and-rescue scene note for a disaster-response "
        "team looking at a mapped area. Describe landmarks, debris, and vehicles "
        f"visible in the image. {context}\n"
        f"Use three short sections with these headings, in order: {sections}. "
        'Write "None seen" under a heading with nothing to report. Only report '
        "what the image or the mapped objects support. Do not give flight advice, "
        "navigation, or any instruction to an aircraft."
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
