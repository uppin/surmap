"""In-memory SlamBackend for tests and simulation-machine replay."""

from __future__ import annotations

from surmap.slam.base import FrameResult
from surmap.types import Pose, StereoFramePair, Vec3


class InMemorySlamBackend:
    """Returns a fixed pose (identity at origin by default), no points."""

    def __init__(self, pose: Pose | None = None) -> None:
        self._pose = pose if pose is not None else Pose(Vec3(0.0, 0.0, 0.0))
        self._trajectory: list[Pose] = []
        self.closed = False

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self._trajectory.append(self._pose)
        return FrameResult(frame.frame_id, frame.t_ns, self._pose, ())

    def trajectory(self) -> list[Pose]:
        return list(self._trajectory)

    def close(self) -> None:
        self.closed = True
