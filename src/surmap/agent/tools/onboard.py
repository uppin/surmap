"""`OnboardModels`: the on-board detector models a station's runs can process their frames with.

The models are the Coral profiles (`surmap.detection.profiles`); a station has one when its
prepared model dir holds the profile's CPU twin and the COCO labels. Every run builds its own
detection source, so no tracker state carries from one run into the next.

Passive survey only (docs/architecture.md section 1): the choice decides what processes recorded
frames; nothing here commands a vehicle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from surmap.demo.server import coral_detection_source
from surmap.detection import MODEL_PROFILES, DetectionSource, DetectorUnavailable

__all__ = [
    "ONBOARD_OFF",
    "OnboardModel",
    "OnboardModels",
    "OnboardUnavailable",
    "SourceBuilder",
]

ONBOARD_OFF = "none"
"""The choice that runs no on-board model."""

_LABELS_FILE = "coco_labels.txt"

SourceBuilder = Callable[[Path, str], DetectionSource]
"""Builds the detection source of one profile from a prepared model dir."""


@dataclass(frozen=True)
class OnboardModel:
    """One on-board model, and whether this station can run it."""

    name: str
    title: str
    note: str
    available: bool
    is_default: bool
    classes: tuple[str, ...] = ()
    """The object classes it can recognise; it detects nothing else."""

    def recognises(self, concept: str) -> bool:
        """Whether `concept` (a SAM prompt such as "car" or "cars") is one of its classes."""
        name = concept.strip().lower()
        return name in self.classes or (name.endswith("s") and name[:-1] in self.classes)


class OnboardUnavailable(RuntimeError):
    """A known on-board model this station cannot run: its files or runtime are missing."""


class OnboardModels:
    """The Coral profiles in `model_dir`, with `default` run when a run names no model.

    With no `model_dir` no model is available, so `default` must be None.
    """

    def __init__(
        self,
        model_dir: Path | None = None,
        *,
        default: str | None = None,
        build: SourceBuilder = coral_detection_source,
    ) -> None:
        if default is not None:
            self._known(default)
        self._model_dir = model_dir
        self.default = default
        self._build = build

    def models(self) -> tuple[OnboardModel, ...]:
        """Every profile in catalogue order."""
        return tuple(
            OnboardModel(
                name=profile.name,
                title=profile.title,
                note=profile.note,
                available=self._available(profile.name),
                is_default=profile.name == self.default,
                classes=profile.classes,
            )
            for profile in MODEL_PROFILES.values()
        )

    def resolve(self, choice: str | None) -> str | None:
        """The model a run with `choice` uses: `default` when None, None for `ONBOARD_OFF`.

        `ValueError` for a name no profile has.
        """
        if choice is None:
            return self.default
        if choice == ONBOARD_OFF:
            return None
        return self._known(choice)

    def source(self, model: str) -> DetectionSource:
        """A fresh detection source running `model`; `OnboardUnavailable` when the station
        cannot run it."""
        if self._model_dir is None or not self._available(model):
            raise OnboardUnavailable(
                f"this station has no files for on-board model {model!r}; run "
                "`uv run python scripts/fetch_coral_model.py` and pass --coral-model-dir"
            )
        try:
            return self._build(self._model_dir, model)
        except DetectorUnavailable as unavailable:
            raise OnboardUnavailable(str(unavailable)) from unavailable

    def _available(self, model: str) -> bool:
        if self._model_dir is None:
            return False
        profile = MODEL_PROFILES[model]
        return (self._model_dir / profile.cpu_file).is_file() and (
            self._model_dir / _LABELS_FILE
        ).is_file()

    @staticmethod
    def _known(model: str) -> str:
        if model not in MODEL_PROFILES:
            choices = ", ".join([*MODEL_PROFILES, ONBOARD_OFF])
            raise ValueError(f"no on-board model {model!r}; choose one of {choices}")
        return model
