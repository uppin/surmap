"""Map question hook.

`POST /ask` calls `answer_map_question`. The default matches landmark
labels locally and cites their mask clouds. A Muse Spark caller replaces
this function. `SURMAP_LIVE_MAP_QA` does not place a network call in
this build.
"""

from __future__ import annotations

import os
import re

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


def answer_map_question(question: str, snapshot: SemanticMapSnapshot) -> AskAnswer:
    """Cite tracks whose label or description matches the question.

    This is the offline hook. It does not call a model.
    """
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
            "Map Q&A is a local label match until a Muse Spark hook replaces "
            "surmap.viewer.ask.answer_map_question."
        )
    else:
        answer = "No semantic map snapshot is loaded."
    if os.environ.get("SURMAP_LIVE_MAP_QA", "").strip() not in ("", "0"):
        answer = "SURMAP_LIVE_MAP_QA is set; this build does not call a model. " + answer
    return AskAnswer(answer, ids, tuple(points))


def _tokens(question: str) -> tuple[str, ...]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    return tuple(word for word in words if word not in _STOPWORDS and len(word) > 1)
