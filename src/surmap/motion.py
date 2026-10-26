"""Static vs moving classification for reconstructed object tracks.

An object is moving when its map-frame centroid displaces by more than
``threshold_m`` between first and last observation, after camera
ego-motion has already been compensated by the RTAB-Map poses used to
place the points in the map frame (docs/architecture.md section 3.3).
"""

from __future__ import annotations

from surmap.types import Motion, ObjectTrack3D


def classify_motion(
    track: ObjectTrack3D,
    threshold_m: float = 0.5,
    min_observations: int = 2,
) -> Motion:
    if threshold_m < 0:
        raise ValueError("threshold_m must be non-negative")
    if len(track.observations) < min_observations:
        return Motion.UNKNOWN
    displacement = (track.observations[-1].centroid - track.observations[0].centroid).norm()
    return Motion.MOVING if displacement > threshold_m else Motion.STATIC
