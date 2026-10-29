"""Map question hook.

`POST /ask` calls `answer_map_question`. With `SURMAP_LIVE_META=1` and
an importable `surmap.mapqa`, the question is delegated to
`surmap.mapqa.answer(question, snapshot_path=...)`, which returns the
same `{answer, landmark_ids, highlight_points}` object. Otherwise the
answer is a local label match. This module does not call a model itself.
"""

from __future__ import annotations

import importlib
import os
import re
from collections.abc import Callable
from typing import cast

from surmap.types import Vec3
from surmap.viewer.model import SemanticMapSnapshot

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
_LIVE_META = "SURMAP_LIVE_META"


class AskAnswer:
    """JSON body of `POST /ask`."""

    def __init__(
        self, answer: str, landmark_ids: tuple[str, ...], highlight_points: tuple[Vec3, ...]
    ) -> None:
        self.answer = answer
        self.landmark_ids = landmark_ids
        self.highlight_points = highlight_points

    def as_json(self) -> dict[str, object]:
        return {
            "answer": self.answer,
            "landmark_ids": list(self.landmark_ids),
            "highlight_points": [
                {"x": point.x, "y": point.y, "z": point.z} for point in self.highlight_points
            ],
        }


def answer_map_question(
    question: str,
    snapshot: SemanticMapSnapshot,
    *,
    snapshot_path: str | None = None,
) -> AskAnswer:
    """Answer one map question.

    Live Muse Spark Q&A is `surmap.mapqa.answer` when that package
    imports and `SURMAP_LIVE_META=1`. Any other case uses the label match.
    """
    if os.environ.get(_LIVE_META, "").strip() == "1":
        delegated = _delegate_mapqa(question, snapshot_path)
        if delegated is not None:
            return delegated
    return _local_match(question, snapshot)


def _delegate_mapqa(question: str, snapshot_path: str | None) -> AskAnswer | None:
    try:
        module = importlib.import_module("surmap.mapqa")
    except ImportError:
        return None
    answer_fn = _mapqa_answer(module)
    if answer_fn is None:
        return None
    return _from_contract(answer_fn(question, snapshot_path=snapshot_path))


def _mapqa_answer(module: object) -> Callable[..., object] | None:
    candidate = getattr(module, "answer", None)
    if not callable(candidate):
        return None
    return cast(Callable[..., object], candidate)


def _from_contract(raw: object) -> AskAnswer:
    if not isinstance(raw, dict):
        raise ValueError("surmap.mapqa.answer must return an object")
    fields = {str(key): value for key, value in raw.items()}
    answer = fields.get("answer")
    if not isinstance(answer, str):
        raise ValueError("surmap.mapqa.answer must include a string answer")
    ids = _strings(fields.get("landmark_ids"), "landmark_ids")
    raw_points = _items(fields.get("highlight_points"), "highlight_points")
    return AskAnswer(answer, tuple(ids), tuple(_xyz(item) for item in raw_points))


def _strings(value: object, field: str) -> list[str]:
    items = _items(value, field)
    texts: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"surmap.mapqa {field} must be a list of strings")
        texts.append(item)
    return texts


def _items(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"surmap.mapqa {field} must be a list")
    return value


def _xyz(value: object) -> Vec3:
    if not isinstance(value, dict):
        raise ValueError("surmap.mapqa highlight_points entries must be objects")
    fields = {str(key): item for key, item in value.items()}
    return Vec3(_float(fields.get("x")), _float(fields.get("y")), _float(fields.get("z")))


def _float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("surmap.mapqa highlight point coordinates must be numbers")
    return float(value)


def _local_match(question: str, snapshot: SemanticMapSnapshot) -> AskAnswer:
    tokens = _tokens(question)
    matched = [
        track
        for track in snapshot.tracks()
        if any(token in f"{track.label} {track.description}".lower() for token in tokens)
    ]
    ids = tuple(track.id for track in matched)
    points: list[Vec3] = []
    for track in matched:
        if track.mask_points:
            points.extend(track.mask_points)
        else:
            points.append(track.xyz)
    if matched:
        labels = ", ".join(f"{track.label} ({track.id})" for track in matched)
        answer = f"Matched {len(matched)} track(s): {labels}."
    elif snapshot.tracks():
        answer = (
            "No landmark label matches that question. "
            "Map Q&A uses a local label match unless SURMAP_LIVE_META=1 "
            "and surmap.mapqa is installed."
        )
    else:
        answer = "No semantic map snapshot is loaded."
    return AskAnswer(answer, ids, tuple(points))


def _tokens(question: str) -> tuple[str, ...]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    return tuple(word for word in words if word not in _STOPWORDS and len(word) > 1)
