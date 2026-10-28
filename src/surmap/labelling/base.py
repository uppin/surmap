"""Label port for one mapped object.

The survey asks a labelling client for a short name a search-and-rescue
team can read. Adapters translate provider responses into `ObjectLabel`.
Pipeline code depends on this port, not on a provider SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from surmap.types import Vec3


@dataclass(frozen=True)
class ObjectLabel:
    """One semantic label for one object, already parsed from provider text."""

    label: str
    description: str
    confidence: float | None
    model_id: str
    raw_text: str


@runtime_checkable
class LabelClient(Protocol):
    """Names one JPEG crop in the civilian disaster-response survey."""

    def label_object(self, crop_jpeg: bytes, coarse_label: str, map_xyz: Vec3) -> ObjectLabel:
        """Label one crop.

        `crop_jpeg` is a JPEG byte string. `coarse_label` is the detector's
        word for the box. `map_xyz` is the object's position in the map
        frame, in metres.
        """
        ...
