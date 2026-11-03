"""What a SLAM backend can do beyond `SlamBackend`, as typed, runtime-checkable protocols.

A batch backend (the RTAB-Map sidecar) only knows its poses once the stream is staged, so it
`flush`es. A live backend (the streaming sidecar) reports odometry per frame while frames play,
emits keyframes, holds a map snapshot and knows its stereo rectification. The CM5 checks each with
`isinstance` and serves what the backend offers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from surmap.slam.base import FrameResult
from surmap.slam.stream_protocol import MapUpdate, OdomUpdate, Rectification
from surmap.types import Vec3

__all__ = [
    "FlushableBackend",
    "KeyframeSource",
    "MapSnapshotSource",
    "OdometrySource",
    "RectificationSource",
]


@runtime_checkable
class OdometrySource(Protocol):
    def frame_odometry(self, frame_id: int) -> OdomUpdate | None:
        """The odometry that landed for `frame_id`, or None while it has not."""
        ...


@runtime_checkable
class KeyframeSource(Protocol):
    def poll_updates(self) -> list[MapUpdate]:
        """Map updates (keyframes, graph corrections) that landed since the last poll."""
        ...


@runtime_checkable
class MapSnapshotSource(Protocol):
    def map_snapshot(self) -> tuple[Vec3, ...]:
        """Every map point the backend holds now."""
        ...


@runtime_checkable
class RectificationSource(Protocol):
    @property
    def rectification(self) -> Rectification | None:
        """The left camera's stereo rectification, once the backend has computed it."""
        ...


@runtime_checkable
class FlushableBackend(Protocol):
    def flush(self) -> list[FrameResult]:
        """Finish the staged stream and return the results it could only compute at the end."""
        ...
