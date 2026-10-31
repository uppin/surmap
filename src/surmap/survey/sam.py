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

import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
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


@runtime_checkable
class VideoSamDetector(Protocol):
    """The continuous (video) segmentation port: sequential frames in.

    One detector serves one whole video: `reset()` starts a new video,
    `track()` is then called once per frame, strictly in frame order,
    and the returned detections carry track ids that persist while an
    object stays visible. Unlike `SamDetector`, calls are synchronous
    and stateful — video mode is a session, not per-frame inference.
    `reset(prompt=...)` names the concept the new video looks for;
    `None` keeps the adapter's configured one.
    """

    def reset(self, prompt: str | None = None) -> None: ...
    def track(self, frame: RawFrame) -> tuple[SamDetection, ...]: ...
    def close(self) -> None: ...


@runtime_checkable
class VideoSamStreamer(Protocol):
    """Whole-video SAM: a video's frames in, per-frame detections out.

    SAM 3.1's native continuous mode is a session over a whole video
    (prompt once, propagate), so this port streams: `stream()` takes
    the video's frame image files in playback order and yields
    `(frame_index, detections)` in frame order, where `frame_index`
    is 0-based into that sequence and detections carry the model's
    own persistent object ids. `prompt` names the concept this video
    looks for; `None` keeps the adapter's configured one.
    """

    def stream(
        self, frame_paths: Sequence[Path], prompt: str | None = None
    ) -> Iterator[tuple[int, tuple[SamDetection, ...]]]: ...
    def close(self) -> None: ...


class AnalysisGate:
    """Admits one analysis at a time, per the stream's `AnalysisMode`."""

    def __init__(self, mode: AnalysisMode) -> None:
        self._mode = mode
        self._lock = asyncio.Lock()
        self.dropped = 0

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[bool]:
        """`True` when the caller may analyze; `False` when the frame drops."""
        if self._mode is AnalysisMode.BEST_EFFORT_DROP and self._lock.locked():
            self.dropped += 1
            yield False
            return
        await self._lock.acquire()
        try:
            yield True
        finally:
            self._lock.release()


class InMemorySamDetector:
    """`SamDetector` adapter for tests and simulation: configured output."""

    def __init__(self, detections: tuple[SamDetection, ...] = ()) -> None:
        self._detections = detections
        self.frames: list[RawFrame] = []

    async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        self.frames.append(frame)
        return self._detections


class InMemoryVideoSamDetector:
    """`VideoSamDetector` adapter for tests and simulation: configured output.

    Records every tracked frame in order; a configured detection without
    a track id gains the persistent id of its position (1-based), as a
    real video session would assign on first sight.
    """

    def __init__(self, detections: tuple[SamDetection, ...] = ()) -> None:
        self._detections = detections
        self.frames: list[RawFrame] = []
        self.prompts: list[str | None] = []

    def reset(self, prompt: str | None = None) -> None:
        self.frames = []
        self.prompts.append(prompt)

    def track(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        self.frames.append(frame)
        return tuple(
            detection if detection.track_id is not None else replace(detection, track_id=index + 1)
            for index, detection in enumerate(self._detections)
        )

    def close(self) -> None:
        pass


class InMemoryVideoSamStreamer:
    """`VideoSamStreamer` adapter for tests and simulation: configured output."""

    def __init__(self, detections: tuple[SamDetection, ...] = ()) -> None:
        self._detections = detections
        self.videos: list[list[Path]] = []
        self.prompts: list[str | None] = []

    def stream(
        self, frame_paths: Sequence[Path], prompt: str | None = None
    ) -> Iterator[tuple[int, tuple[SamDetection, ...]]]:
        self.videos.append(list(frame_paths))
        self.prompts.append(prompt)
        for index in range(len(frame_paths)):
            yield (
                index,
                tuple(
                    detection
                    if detection.track_id is not None
                    else replace(detection, track_id=position + 1)
                    for position, detection in enumerate(self._detections)
                ),
            )

    def close(self) -> None:
        pass


class CentredBoxVideoSamDetector:
    """`VideoSamDetector` stand-in with no model: one fixed object per frame.

    Outlines the centre of every frame (the middle `fraction` of its
    width and height) as track 1, so the downstream path — region
    queries, the 3D region layer — runs without a GPU or SAM weights.
    """

    def __init__(self, label: str = "object", fraction: float = 0.3) -> None:
        self._label = label
        self._fraction = fraction

    def reset(self, prompt: str | None = None) -> None:
        if prompt is not None:
            self._label = prompt

    def track(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        half_w = frame.width * self._fraction / 2
        half_h = frame.height * self._fraction / 2
        cx, cy = frame.width / 2, frame.height / 2
        x0, y0, x1, y1 = cx - half_w, cy - half_h, cx + half_w, cy + half_h
        return (
            SamDetection(
                self._label,
                1.0,
                (x0, y0, x1, y1),
                ((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
                track_id=1,
            ),
        )

    def close(self) -> None:
        pass
