"""The JSON object ``ask`` returns to a responder and to the web viewer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HighlightPoint:
    """One lat/lon the viewer should mark. Degrees, WGS84."""

    lat: float
    lon: float


@dataclass(frozen=True)
class MapAnswer:
    """Strict answer: prose plus the ids and coordinates it cites."""

    answer: str
    landmark_ids: tuple[str, ...]
    highlight_points: tuple[HighlightPoint, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "answer": self.answer,
            "landmark_ids": list(self.landmark_ids),
            "highlight_points": [
                {"lat": point.lat, "lon": point.lon} for point in self.highlight_points
            ],
        }


@dataclass(frozen=True)
class ModelUsage:
    """Token counts from a responses-API ``usage`` object.

    ``reasoning_tokens`` is ``output_tokens_details.reasoning_tokens`` and is
    already included in ``output_tokens``.
    """

    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None
