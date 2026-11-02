"""One map object per physical thing seen across frames.

SAM 3.1 runs on every frame, so one survivor seen in 30 frames gives 30
masks. ``ObjectMerger`` feeds each mask's map-frame points to a
``SurfaceMap`` (``surmap.survey.surfaces``: voxel overlap continues a
surface, a 40 cm centroid drift marks it moving), one map per coarse
label so a person never continues a car. The mission labels an object
with a model only when its surface first appears, or when it turns
moving. Later sightings add an observation to the same track.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from surmap.motion import classify_motion
from surmap.survey.surfaces import SurfaceMap
from surmap.types import ObjectTrack3D, Vec3


@dataclass(frozen=True)
class Sighting:
    """Where one mask went. ``track_id`` is None for a surface not yet bound."""

    label: str
    surface_id: int
    track_id: int | None
    moving: bool
    turned_moving: bool


class ObjectMerger:
    def __init__(self) -> None:
        self._maps: dict[str, SurfaceMap] = {}
        self._tracks: dict[tuple[str, int], int] = {}
        self._moving: set[tuple[str, int]] = set()

    def observe(self, frame_id: int, label: str, points: Sequence[Vec3]) -> Sighting | None:
        """Assign one mask's map points. None when there are no points."""
        if not points:
            return None
        surfaces = self._maps.setdefault(label, SurfaceMap())
        array = np.array([(p.x, p.y, p.z) for p in points], dtype=np.float32)
        assignment = surfaces.assign(frame_id, 0, label, array)
        if assignment is None:
            return None
        key = (label, assignment.surface_id)
        turned = assignment.moving and key not in self._moving and key in self._tracks
        if assignment.moving:
            self._moving.add(key)
        return Sighting(
            label=label,
            surface_id=assignment.surface_id,
            track_id=self._tracks.get(key),
            moving=assignment.moving,
            turned_moving=turned,
        )

    def bind(self, sighting: Sighting, track_id: int) -> None:
        self._tracks[(sighting.label, sighting.surface_id)] = track_id


def object_summary(tracks: Sequence[ObjectTrack3D]) -> tuple[str, ...]:
    """One line per track for the scene-note prompt: label, motion, frames, position."""
    lines: list[str] = []
    for track in tracks:
        if not track.observations:
            continue
        last = track.observations[-1].centroid
        frames = len({item.frame_id for item in track.observations})
        lines.append(
            f"{track.label}, {classify_motion(track).value}, seen in {frames} frame(s), "
            f"map x={last.x:.1f} m y={last.y:.1f} m z={last.z:.1f} m"
        )
    return tuple(lines)
