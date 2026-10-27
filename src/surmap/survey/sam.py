"""Station SAM seam: detector port, analysis admission policy, fake.

SAM 3.1 (docs/architecture.md section 3.1) is a model dependency on the
base station, so it sits behind the `SamDetector` port — the hexagon
shape of `surmap.slam.SlamBackend`. The domain speaks `RawFrame` and
`SamDetection`; a SAM adapter translates at its edge. `InMemorySamDetector`
is the test/simulation adapter.

`AnalysisGate` is the requester's trade-off, enforced: analyze every
frame and accept the lag, or analyze only when the detector is free and
accept (counted) drops.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RawFrame:
    """One raw video frame as the detector consumes it."""

    frame_id: int
    t_ns: int
    channel: int
    width: int
    height: int
    encoding: str
    data: bytes


@dataclass(frozen=True)
class SamDetection:
    """One SAM detection: label, box, mask outline, optional on-board track."""

    label: str
    score: float
    box_xyxy: tuple[float, float, float, float]
    mask_polygon: tuple[tuple[float, float], ...] = ()
    track_id: int | None = None


class AnalysisMode(Enum):
    """Whether the stream analyzes every frame or drops under load."""

    EVERY_FRAME = "every_frame"
    BEST_EFFORT_DROP = "best_effort_drop"


@runtime_checkable
class SamDetector(Protocol):
    """The segmentation port: one frame in, its detections out."""

    async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]: ...


class AnalysisGate:
    """Admits one analysis at a time, per the stream's `AnalysisMode`."""

    def __init__(self, mode: AnalysisMode) -> None:
        self._mode = mode
        self.dropped = 0

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[bool]:
        """`True` when the caller may analyze; `False` when the frame drops."""
        raise NotImplementedError("TODO(pr-3): implement AnalysisGate.slot")
        yield False  # unreachable; keeps the context-manager shape typed


class InMemorySamDetector:
    """`SamDetector` adapter for tests and simulation: configured output."""

    def __init__(self, detections: tuple[SamDetection, ...] = ()) -> None:
        self._detections = detections
        self.frames: list[RawFrame] = []

    async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        raise NotImplementedError("TODO(pr-3): implement InMemorySamDetector.detect")
