"""Object-point seam for the CM5: tracked objects' 3D points, per pair.

The hexagon shape of `surmap.slam.SlamBackend`: the Coral detector/tracker
and stereo reconstruction (docs/architecture.md section 3.3) will implement
this port on hardware; tests and simulation use the in-memory adapter.
Points arrive already in the map frame (transformed by the RTAB-Map pose
at the frame's timestamp); they are layered onto RTAB-Map's output and
never fed back into it (section 6).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from surmap.types import ObjectPoints, Pose, StereoFramePair


@runtime_checkable
class ObjectPointSource(Protocol):
    """Per completed stereo pair: each tracked object's map-frame points."""

    def points_for_pair(
        self, pair: StereoFramePair, pose: Pose | None
    ) -> tuple[ObjectPoints, ...]: ...


class InMemoryObjectPointSource:
    """`ObjectPointSource` adapter for tests and simulation: configured output."""

    def __init__(self, observations: tuple[ObjectPoints, ...] = ()) -> None:
        self._observations = observations
        self.pairs: list[StereoFramePair] = []

    def points_for_pair(self, pair: StereoFramePair, pose: Pose | None) -> tuple[ObjectPoints, ...]:
        self.pairs.append(pair)
        return self._observations
