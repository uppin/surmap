"""In-memory labelling client for tests and session replay.

Returns a label the caller already recorded. It never opens a socket
and never reads `BASETEN_API_KEY`.
"""

from __future__ import annotations

from surmap.labelling.base import ObjectLabel
from surmap.types import Vec3


class InMemoryLabelClient:
    """LabelClient that repeats one recorded label."""

    def __init__(self, label: ObjectLabel) -> None:
        self._label = label

    def label_object(self, crop_jpeg: bytes, coarse_label: str, map_xyz: Vec3) -> ObjectLabel:
        """Return the recorded label. The crop and position are ignored."""
        return self._label
