"""Stage 6: retrospective map-frame placement (design section 4 step 6).

TODO(n5): implemented by pr-5-moving-placement's Green row.
"""

from __future__ import annotations

from dataclasses import dataclass

from surmap.moving.buffer import Observation
from surmap.types import Pose, Vec3

AREA_TRACK_ID_BASE = 1_000_000


@dataclass(frozen=True)
class KeyframePose:
    """One optimized keyframe pose from the RTAB flush."""

    t_ns: int
    pose: Pose


@dataclass(frozen=True)
class PlacedSnapshot:
    """One buffered observation placed in the map frame."""

    frame_id: int
    t_ns: int
    object_track_id: int
    identity_source: str  # DETECTOR | AREA_ALLOCATED
    keypoints: tuple[Vec3, ...]
    centroid: Vec3


def distribute_correction(
    observations: tuple[Observation, ...],
    keyframes: tuple[KeyframePose, ...],
) -> tuple[Pose, ...]:
    """Camera pose per observation, keyframe correction over VO increments."""
    raise NotImplementedError("TODO(n5): distribute_correction")


def object_track_id(detector_track_id: int | None, area_track_id: int) -> tuple[int, str]:
    """Designation source: adopted detector ID or disjoint area allocation."""
    raise NotImplementedError("TODO(n5): object_track_id")
