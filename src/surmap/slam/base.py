"""SLAM backend interface.

One backend provides, per processed stereo frame: the camera pose in
the map frame and the static-scene points observed in that frame.
Object points are never fed into a backend (docs/architecture.md
section 6); they are layered onto the backend's output downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from surmap.types import Pose, StereoFramePair, Vec3


@dataclass(frozen=True)
class FrameResult:
    frame_id: int
    t_ns: int
    pose: Pose | None  # None when pose is not (yet) estimated
    static_points: tuple[Vec3, ...] = ()  # map-frame static-scene points


@runtime_checkable
class SlamBackend(Protocol):
    def process_frame(self, frame: StereoFramePair) -> FrameResult: ...

    def trajectory(self) -> list[Pose]: ...

    def close(self) -> None: ...
