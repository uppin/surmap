"""The `SurveyWorkspace` port the SurMap tools run against, and the SurMap types it speaks.

The port speaks SurMap's own types (scenes, runs, frames, SAM detections, stored objects); the
tool handlers in `surmap.agent.tools.handlers` turn those into `surmap.agent.v1` messages.
`surmap.agent.tools.workspace.DemoWorkspace` is the default adapter.

Read/run only (docs/architecture.md section 1): a workspace launches demo runs and reads their
results; nothing here commands a vehicle or writes into RTAB-Map's map.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from surmap.agent.tools.onboard import OnboardModel
from surmap.demo.gallery import GalleryEntry
from surmap.objects3d import UpAxis
from surmap.survey.sam import SamDetection

__all__ = [
    "OBJECT_FRAME",
    "OBJECT_UP_AXIS",
    "BoxXYXY",
    "FrameDetections",
    "GalleryEntry",
    "FrameImage",
    "FrameRecord",
    "FrameSource",
    "ObjectBox",
    "OnboardModel",
    "RunBusy",
    "RunInfo",
    "RunStatus",
    "SceneInfo",
    "StoredObject",
    "SurveyWorkspace",
]

BoxXYXY = tuple[float, float, float, float]
"""A pixel box: left, top, right, bottom."""

OBJECT_FRAME = "map"
"""The coordinate frame object points are in: the run's RTAB-Map map."""

OBJECT_UP_AXIS: UpAxis = "-y"
"""The map's up axis, as the demo's RTAB-Map map is laid out."""


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
    onboard_model: str = ""
    """The on-board detector model that processed its frames; empty when it ran none."""


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


class RunBusy(RuntimeError):
    """A run cannot start: the station's previous run did not stop in time."""


class SurveyWorkspace(Protocol):
    """What the SurMap tools need from a station: scenes, runs, frames, SAM and objects."""

    def scenes(self) -> Sequence[SceneInfo]:
        """Every scene this station can run, in catalogue order."""
        ...

    def datasets(self) -> Sequence[GalleryEntry]:
        """Every dataset in the gallery catalogue, in catalogue order."""
        ...

    def dataset(self, dataset_id: str) -> GalleryEntry | None:
        """The dataset `dataset_id`, or None when the catalogue does not offer it."""
        ...

    def dataset_thumbnail(self, dataset_id: str) -> bytes | None:
        """The dataset's thumbnail JPEG, or None when it is not prepared."""
        ...

    async def prepare_dataset(self, dataset_id: str) -> GalleryEntry:
        """Download and prepare `dataset_id`; `KeyError` for an unknown dataset."""
        ...

    def onboard_models(self) -> Sequence[OnboardModel]:
        """Every on-board detector model, in catalogue order, with this station's availability."""
        ...

    async def run_rtabmap(
        self,
        dataset: str,
        *,
        max_frames: int | None,
        fps: float | None,
        onboard_model: str | None,
    ) -> RunInfo:
        """Run RTAB-Map (no SAM) on `dataset` and return the recorded run when it ends.

        `onboard_model` is as `run_demo` takes it.
        """
        ...

    async def run_sam_on_dataset(
        self, dataset: str, concept: str | None, *, max_frames: int | None
    ) -> Sequence[FrameDetections]:
        """SAM, looking for `concept`, on evenly spaced frames of `dataset` itself.

        No RTAB-Map and no recorded run: the dataset is prepared first when
        needed. `KeyError` for an unknown dataset.
        """
        ...

    async def run_demo(
        self,
        dataset: str,
        prompt: str | None,
        *,
        max_frames: int | None,
        fps: float | None,
        onboard_model: str | None,
    ) -> RunInfo:
        """Run `dataset` headlessly with SAM looking for `prompt` and return when it ends.

        `onboard_model` names the on-board detector model that processes the frames: a profile
        name, `ONBOARD_OFF` for none, or None for the station default. Prepares the scene first
        when it is not cached. Cancelling the call stops the run. Raises `KeyError` for a scene
        the station does not offer, `RunBusy` when the previous run does not stop in time,
        `ValueError` for a non-positive `fps` or an unknown model, and `OnboardUnavailable` for
        a model this station cannot run.
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
