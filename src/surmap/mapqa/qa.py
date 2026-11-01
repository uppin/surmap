"""Ask a semantic map a question, write a situation report, or ask by voice."""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Mapping
from pathlib import Path

from surmap.mapqa.answers import HighlightPoint, MapAnswer
from surmap.mapqa.client import (
    _AUTO_LEDGER,
    DEFAULT_MODEL,
    MIN_MAX_OUTPUT_TOKENS,
    BeforeCall,
    Clock,
    HttpTransport,
    MetaClient,
    OnUsage,
)
from surmap.mapqa.errors import InvalidMapAnswer, ModelApiError
from surmap.mapqa.snapshot import MapFeature, MapSnapshot, Xyz, load_snapshot

_LIVE_META = "SURMAP_LIVE_META"
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "where",
        "is",
        "are",
        "was",
        "what",
        "which",
        "show",
        "me",
        "of",
        "in",
        "on",
        "at",
    }
)

_ASK_INSTRUCTIONS = (
    "You are a humanitarian search-and-rescue assistant reading one civilian "
    "semantic map. Responders use your answer to find people and blocked routes. "
    "Use only the objects in the snapshot. Do not invent landmarks. "
    "Reply with one JSON object and no markdown, no code fence, and no prose around it. "
    'The object has exactly these fields: "answer" (string), '
    '"landmark_ids" (array of id strings from the snapshot), '
    '"highlight_points" (array of {"lat": number, "lon": number} for those objects). '
    "Cite every object the answer depends on, including dynamic objects. "
    "Copy lat and lon from the snapshot. "
    "This is civilian disaster response only."
)

_REPORT_INSTRUCTIONS = (
    "You are a humanitarian search-and-rescue assistant. "
    "Write a Markdown situation report for civilian responders from the snapshot. "
    "Cover damaged structures, people who may need rescue, blocked access, and vehicles. "
    "Cite object ids and coordinates from the snapshot. Do not invent objects. "
    "Civilian disaster response only."
)


class MapQa:
    """Questions over one loaded snapshot. The model call is behind ``MetaClient``."""

    def __init__(
        self,
        snapshot: MapSnapshot | str | Path,
        *,
        api_key: str | None = None,
        model: str | None = None,
        transport: HttpTransport | None = None,
        before_call: BeforeCall | None = None,
        on_usage: OnUsage | None = None,
        usage_ledger: object | None = _AUTO_LEDGER,
        max_output_tokens: int = MIN_MAX_OUTPUT_TOKENS,
        clock: Clock | None = None,
        timeout_s: float = 180.0,
    ) -> None:
        self.snapshot = snapshot if isinstance(snapshot, MapSnapshot) else load_snapshot(snapshot)
        self._api_key = api_key
        self._transport = transport
        self._before_call = before_call
        self._on_usage = on_usage
        self._clock = clock
        self._timeout_s = timeout_s
        self._max_output_tokens = max_output_tokens
        self._usage_ledger = usage_ledger
        self._meta = MetaClient(
            api_key=api_key,
            model=model,
            transport=transport,
            before_call=before_call,
            on_usage=on_usage,
            usage_ledger=usage_ledger,
            max_output_tokens=max_output_tokens,
            clock=clock,
            timeout_s=timeout_s,
        )

    def with_snapshot(self, snapshot: MapSnapshot | str | Path) -> MapQa:
        """Same client settings, a different snapshot file."""
        return MapQa(
            snapshot,
            api_key=self._api_key,
            model=self._meta.model,
            transport=self._transport,
            before_call=self._before_call,
            on_usage=self._on_usage,
            usage_ledger=self._meta._ledger,
            max_output_tokens=self._max_output_tokens,
            clock=self._clock,
            timeout_s=self._timeout_s,
        )

    def ask(self, question: str) -> MapAnswer:
        """Return the strict JSON answer, with every cited id checked against the map."""
        text = question.strip()
        if not text:
            raise ValueError("question is required")
        reply = self._meta.complete(_ASK_INSTRUCTIONS, _ask_input(self.snapshot, text))
        return _parse_answer(reply, self.snapshot)

    def report(self) -> str:
        """Markdown situation report for responders. Not JSON."""
        return self._meta.complete(_REPORT_INSTRUCTIONS, _report_input(self.snapshot))

    def ask_voice(self, audio_path: str | Path) -> MapAnswer:
        """Transcribe a WAV recording, then ask that question of the map."""
        path = Path(audio_path)
        try:
            audio = path.read_bytes()
        except OSError as exc:
            raise ModelApiError(f"could not read audio {path}: {exc}") from exc
        transcript = self._meta.transcribe(audio, path.name)
        return self.ask(transcript)


def answer(question: str, snapshot_path: str | Path | None = None) -> dict[str, object]:
    """Answer one question the way the mission-demo viewer calls it.

    ``answer(question, snapshot_path=...)`` returns
    ``{answer, landmark_ids, highlight_points}``. Each highlight point is
    map-frame metres, ``{"x", "y", "z"}``.

    A live Meta call runs only when ``SURMAP_LIVE_META=1``. Otherwise the
    same ``MapQa.ask`` parser reads a deterministic label-match fixture
    and does not open a socket.
    """
    if snapshot_path is None:
        return {
            "answer": "No semantic map snapshot is loaded.",
            "landmark_ids": [],
            "highlight_points": [],
        }
    if _live_meta():
        qa = MapQa(snapshot_path)
    else:
        snapshot = load_snapshot(snapshot_path)
        qa = MapQa(
            snapshot,
            api_key="offline",
            model=DEFAULT_MODEL,
            transport=_FixtureTransport(_responses_bytes(_offline_fixture(question, snapshot))),
            usage_ledger=None,
        )
    asked = qa.ask(question)
    return _viewer_dict(asked, qa.snapshot)


class _FixtureTransport:
    """Returns one recorded responses body. Never opens a socket."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        del url, headers, body
        return self._body


def _live_meta() -> bool:
    return os.environ.get(_LIVE_META, "").strip() == "1"


def _offline_fixture(question: str, snapshot: MapSnapshot) -> str:
    matched = _matched_features(question, snapshot)
    points = [
        {"lat": item.lat, "lon": item.lon}
        for item in matched
        if item.lat is not None and item.lon is not None
    ]
    return json.dumps(
        {
            "answer": _offline_text(matched, snapshot),
            "landmark_ids": [item.id for item in matched],
            "highlight_points": points,
        }
    )


def _offline_text(matched: tuple[MapFeature, ...], snapshot: MapSnapshot) -> str:
    if matched:
        labels = ", ".join(f"{item.label} ({item.id})" for item in matched)
        return f"Matched {len(matched)} track(s): {labels}."
    if snapshot.landmarks or snapshot.dynamic:
        return (
            "No landmark label matches that question. "
            "Map Q&A uses a local label match unless SURMAP_LIVE_META=1."
        )
    return "No semantic map snapshot is loaded."


def _matched_features(question: str, snapshot: MapSnapshot) -> tuple[MapFeature, ...]:
    tokens = _tokens(question)
    return tuple(
        item
        for item in (*snapshot.landmarks, *snapshot.dynamic)
        if any(_mentions(token, f"{item.label} {item.description}".lower()) for token in tokens)
    )


def _tokens(question: str) -> tuple[str, ...]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    return tuple(word for word in words if word not in _STOPWORDS and len(word) > 1)


def _mentions(token: str, text: str) -> bool:
    """True when ``token`` appears in ``text``, including a trailing plural s."""
    if token in text:
        return True
    singular = token[:-1] if len(token) > 3 and token.endswith("s") else ""
    return singular != "" and singular in text


def _responses_bytes(text: str) -> bytes:
    return json.dumps(
        {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
    ).encode()


def _viewer_dict(asked: MapAnswer, snapshot: MapSnapshot) -> dict[str, object]:
    return {
        "answer": asked.answer,
        "landmark_ids": list(asked.landmark_ids),
        "highlight_points": _viewer_points(asked.landmark_ids, snapshot),
    }


def _viewer_points(ids: tuple[str, ...], snapshot: MapSnapshot) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for feature_id in ids:
        feature = snapshot.feature(feature_id)
        if feature is None:
            continue
        cloud: tuple[Xyz, ...] = feature.mask_points if feature.mask_points else (feature.xyz,)
        for point in cloud:
            points.append({"x": point.x, "y": point.y, "z": point.z})
    return points


def _ask_input(snapshot: MapSnapshot, question: str) -> str:
    return f"Semantic map snapshot:\n{_snapshot_text(snapshot)}\n\nQuestion:\n{question}"


def _report_input(snapshot: MapSnapshot) -> str:
    return f"Semantic map snapshot:\n{_snapshot_text(snapshot)}\n\nWrite the situation report."


def _snapshot_text(snapshot: MapSnapshot) -> str:
    objects: list[dict[str, object]] = []
    for layer, items in (("landmarks", snapshot.landmarks), ("dynamic", snapshot.dynamic)):
        for item in items:
            objects.append(_feature_payload(item, layer))
    origin: dict[str, object] | None = None
    if snapshot.origin is not None:
        origin = {
            "lat": snapshot.origin.lat,
            "lon": snapshot.origin.lon,
            "alt": snapshot.origin.alt,
        }
    return json.dumps({"origin": origin, "objects": objects}, ensure_ascii=False)


def _feature_payload(item: MapFeature, layer: str) -> dict[str, object]:
    return {
        "id": item.id,
        "layer": layer,
        "label": item.label,
        "description": item.description,
        "motion": item.motion,
        "lat": item.lat,
        "lon": item.lon,
        "alt": item.alt,
    }


def _parse_answer(text: str, snapshot: MapSnapshot) -> MapAnswer:
    try:
        parsed: object = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise InvalidMapAnswer("model reply was not JSON") from exc
    if not isinstance(parsed, dict):
        raise InvalidMapAnswer("model reply was not a JSON object")
    body: Mapping[str, object] = {str(key): value for key, value in parsed.items()}
    answer = body.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise InvalidMapAnswer("model reply answer must be a non-empty string")
    ids = _landmark_ids(body.get("landmark_ids"), snapshot)
    points = _highlight_points(body.get("highlight_points"))
    if _any_geolocated(ids, snapshot) and not points:
        raise InvalidMapAnswer("cited landmarks include a lat/lon but highlight_points is empty")
    return MapAnswer(answer.strip(), ids, points)


def _landmark_ids(value: object, snapshot: MapSnapshot) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InvalidMapAnswer("landmark_ids must be an array of strings")
    ids: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise InvalidMapAnswer("landmark_ids must be an array of strings")
        if snapshot.feature(item) is None:
            raise InvalidMapAnswer(f"landmark id {item!r} is not on this map")
        if item in ids:
            raise InvalidMapAnswer(f"landmark id {item!r} is duplicated")
        ids.append(item)
    return tuple(ids)


def _highlight_points(value: object) -> tuple[HighlightPoint, ...]:
    if not isinstance(value, list):
        raise InvalidMapAnswer("highlight_points must be an array")
    points: list[HighlightPoint] = []
    for item in value:
        if not isinstance(item, dict):
            raise InvalidMapAnswer("each highlight point must be an object")
        body = {str(key): entry for key, entry in item.items()}
        lat = _coordinate(body.get("lat"), "lat", -90.0, 90.0)
        lon = _coordinate(body.get("lon"), "lon", -180.0, 180.0)
        points.append(HighlightPoint(lat, lon))
    return tuple(points)


def _coordinate(value: object, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidMapAnswer(f"highlight point {name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < low or number > high:
        raise InvalidMapAnswer(f"highlight point {name} is out of range")
    return number


def _any_geolocated(ids: tuple[str, ...], snapshot: MapSnapshot) -> bool:
    for feature_id in ids:
        feature = snapshot.feature(feature_id)
        if feature is not None and feature.lat is not None and feature.lon is not None:
            return True
    return False


__all__ = ["MapQa", "answer"]
