"""The `SurveyWorkspace` port the SurMap tools run against, and its demo adapter.

The port speaks SurMap's own types (scenes, runs, frames, SAM detections, stored objects); the
tool handlers in `surmap.agent.tools.handlers` turn those into `surmap.agent.v1` messages.
`DemoWorkspace` is the default adapter: it drives the demo's `DemoRunHost` headlessly, reads the
run history it records, and publishes object geometry as GLB through a `GeometryStore`.

Read/run only (docs/architecture.md section 1): a workspace launches demo runs and reads their
results; nothing here commands a vehicle or writes into RTAB-Map's map.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from surmap.demo.runs import DemoRunHost
from surmap.survey.sam import SamDetection, VideoSamDetector

__all__ = [
    "BoxXYXY",
    "DemoWorkspace",
    "FrameDetections",
    "FrameImage",
    "FrameRecord",
    "FrameSource",
    "GeometryStore",
    "ObjectBox",
    "RunInfo",
    "RunStatus",
    "SceneInfo",
    "StoredObject",
    "SurveyWorkspace",
]

BoxXYXY = tuple[float, float, float, float]
"""A pixel box: left, top, right, bottom."""


class RunStatus(Enum):
    """Where a demo run is in its life."""

    RUNNING = "running"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    FAILED = "failed"


class FrameSource(Enum):
    """Which image a frame was read from."""

    FULL = "full"
    """The scene's full-resolution recorded frame, from the scene cache."""
    DISPLAY = "display"
    """The run's downscaled display JPEG, from the run history."""


@dataclass(frozen=True)
class SceneInfo:
    """One demo scene the workspace can run."""

    id: str
    title: str
    default_prompt: str
    prepared: bool
    cached_run_id: str | None


@dataclass(frozen=True)
class RunInfo:
    """One run of a demo scene, as its history records it."""

    run_id: str
    dataset: str
    prompt: str
    frames: int
    objects: int
    status: RunStatus


@dataclass(frozen=True)
class FrameRecord:
    """One recorded frame of a run: its position in the run, its id and its timestamp."""

    index: int
    frame_id: int
    t_ns: int


@dataclass(frozen=True)
class FrameDetections:
    """What SAM found on one frame of a run."""

    frame_id: int
    t_ns: int
    detections: tuple[SamDetection, ...]


@dataclass(frozen=True)
class StoredObject:
    """One object a run reconstructed: its accumulated map-frame points and when it was seen.

    `points` are Nx3 metres in the run's map frame (RTAB-Map, up axis `-y`).
    """

    object_id: str
    label: str
    points: NDArray[np.float32]
    moving: bool
    frame_ids: tuple[int, ...]
    t_first_ns: int | None
    t_last_ns: int | None
    confidence: float | None = None


@dataclass(frozen=True)
class ObjectBox:
    """An object's mask box on one frame, in the pixels of the image it was measured on."""

    box_xyxy: BoxXYXY
    measured_on: tuple[int, int]
    """`(width, height)` of the image the box is in."""


@dataclass(frozen=True)
class FrameImage:
    """One frame of a run as an encoded image, whole and uncropped."""

    frame_id: int
    t_ns: int
    data: bytes
    media_type: str
    width: int
    height: int
    source: FrameSource


class SurveyWorkspace(Protocol):
    """What the SurMap tools need from a station: scenes, runs, frames, SAM and objects."""

    def scenes(self) -> Sequence[SceneInfo]:
        """Every scene this station can run, in catalogue order."""
        ...

    async def run_demo(
        self,
        dataset: str,
        prompt: str | None,
        *,
        max_frames: int | None,
        fps: float | None,
    ) -> RunInfo:
        """Run `dataset` headlessly with SAM looking for `prompt` and return when it ends.

        Prepares the scene first when it is not cached. Cancelling the call stops the run.
        Raises `KeyError` for a scene the station does not offer.
        """
        ...

    def run(self, run_id: str) -> RunInfo | None:
        """The run `run_id`, or None when the history has no such run."""
        ...

    def timeline(self, run_id: str) -> Sequence[FrameRecord]:
        """The run's recorded frames in playback order; empty for an unknown run."""
        ...

    async def detect(
        self, run_id: str, concept: str, frame_ids: Sequence[int]
    ) -> Sequence[FrameDetections]:
        """SAM, looking for `concept`, on each of the run's `frame_ids`, in that order.

        Runs on the image `frame` returns, so boxes are in that image's pixels.
        Raises `KeyError` for a frame the run did not record.
        """
        ...

    def objects(self, run_id: str) -> Sequence[StoredObject]:
        """Every object the run reconstructed, by object id; empty for an unknown run."""
        ...

    def object_box(self, run_id: str, object_id: str, frame_id: int) -> ObjectBox | None:
        """The object's recorded SAM mask box on `frame_id`, or None when it is not on it."""
        ...

    def frame(self, run_id: str, frame_id: int) -> FrameImage | None:
        """The frame at full resolution when the scene cache has it, else the display JPEG.

        None when the run did not record `frame_id`.
        """
        ...

    def publish_geometry(self, run_id: str, obj: StoredObject) -> str:
        """Write the object's GLB (once) and return the URI it resolves from."""
        ...


class GeometryStore:
    """GLB files of object geometry, one per `(run_id, object_id)`, under one directory."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def uri(self, run_id: str, object_id: str) -> str:
        """The URI the object's GLB is published at, whether or not it is written yet."""
        raise NotImplementedError  # TODO(pr-7): implement

    def has(self, run_id: str, object_id: str) -> bool:
        """Whether the object's GLB is already written."""
        raise NotImplementedError  # TODO(pr-7): implement

    def put(self, run_id: str, object_id: str, glb: bytes) -> str:
        """Store the object's GLB, replacing any earlier one, and return its URI."""
        raise NotImplementedError  # TODO(pr-7): implement

    def read(self, uri: str) -> bytes | None:
        """The GLB a URI from `uri`/`put` names, or None when nothing is stored there."""
        raise NotImplementedError  # TODO(pr-7): implement


class DemoWorkspace:
    """`SurveyWorkspace` over the demo's run host, its history and its scene cache.

    Runs started here are ordinary demo runs in the host's history database, so the console
    lists them; a headless run takes over a running console run exactly as a new viewer would.
    `detector` answers `detect` on recorded frames. An object's id is `obj_<surface_id>` of the
    history's surface, and its points are every point the run assigned to that surface.
    """

    def __init__(
        self,
        host: DemoRunHost,
        *,
        detector: VideoSamDetector,
        geometry: GeometryStore,
    ) -> None:
        self._host = host
        self._detector = detector
        self.geometry = geometry

    def scenes(self) -> Sequence[SceneInfo]:
        raise NotImplementedError  # TODO(pr-7): implement

    async def run_demo(
        self,
        dataset: str,
        prompt: str | None,
        *,
        max_frames: int | None,
        fps: float | None,
    ) -> RunInfo:
        raise NotImplementedError  # TODO(pr-7): implement

    def run(self, run_id: str) -> RunInfo | None:
        raise NotImplementedError  # TODO(pr-7): implement

    def timeline(self, run_id: str) -> Sequence[FrameRecord]:
        raise NotImplementedError  # TODO(pr-7): implement

    async def detect(
        self, run_id: str, concept: str, frame_ids: Sequence[int]
    ) -> Sequence[FrameDetections]:
        raise NotImplementedError  # TODO(pr-7): implement

    def objects(self, run_id: str) -> Sequence[StoredObject]:
        raise NotImplementedError  # TODO(pr-7): implement

    def object_box(self, run_id: str, object_id: str, frame_id: int) -> ObjectBox | None:
        raise NotImplementedError  # TODO(pr-7): implement

    def frame(self, run_id: str, frame_id: int) -> FrameImage | None:
        raise NotImplementedError  # TODO(pr-7): implement

    def publish_geometry(self, run_id: str, obj: StoredObject) -> str:
        raise NotImplementedError  # TODO(pr-7): implement
