"""SAM 3.1 on Modal as a LADI v2 classifier: one text prompt per class.

Each image is posted to ``MODAL_SAM_URL`` once per concept in
``SAM_CONCEPTS``. A class is predicted when SAM returns at least one
detection scoring ``min_score`` or more (a detection without a score
counts). Classes without a concept are never predicted, and the CLI
drops them from the truth so they do not count against SAM.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from surmap.survey.modal_sam import ModalSamDetector
from surmap.survey.sam import SamDetection

SAM_CONCEPTS: Mapping[str, str] = {
    "buildings_any": "building",
    "buildings_affected_or_greater": "damaged building",
    "debris_any": "debris",
    "flooding_any": "flooded area",
    "bridges_any": "bridge",
    "roads_any": "road",
    "trees_any": "tree",
    "trees_damage": "fallen tree",
    "water_any": "water",
}
DEFAULT_MIN_SCORE = 0.5

Segmenter = Callable[[str, bytes], tuple[SamDetection, ...]]


def _modal_segmenter() -> Segmenter:
    detectors: dict[str, ModalSamDetector] = {}

    def segment(prompt: str, jpeg: bytes) -> tuple[SamDetection, ...]:
        if prompt not in detectors:
            detectors[prompt] = ModalSamDetector(prompt=prompt)
        return detectors[prompt].segment(jpeg, media_type="image/jpeg")

    return segment


class ModalSamLadiClassifier:
    """``LadiClassifier`` backed by SAM 3.1 text prompts on Modal."""

    def __init__(
        self,
        *,
        min_score: float = DEFAULT_MIN_SCORE,
        concepts: Mapping[str, str] = SAM_CONCEPTS,
        segmenter: Segmenter | None = None,
    ) -> None:
        self._min_score = min_score
        self._concepts = dict(concepts)
        self._segment = segmenter if segmenter is not None else _modal_segmenter()

    @property
    def provider(self) -> str:
        return "modal"

    @property
    def model(self) -> str:
        return "sam-3.1"

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(self._concepts)

    def classify(self, jpeg: bytes) -> frozenset[str]:
        found: set[str] = set()
        for name, prompt in self._concepts.items():
            detections = self._segment(prompt, jpeg)
            if any(d.score is None or d.score >= self._min_score for d in detections):
                found.add(name)
        return frozenset(found)
