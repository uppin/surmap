"""Replay a recorded run from its journal: no RTAB-Map, no SAM.

Frames, map updates, detections and SAM results are played back exactly
as they were journalled (`RunHistoryStore.journal`). The segmentation —
each SAM mask's region in 3D and its assignment to object surfaces — is
computed again by the current code: regions from RTAB-Map's journalled
dense buffer (`surmap.slam.dense.DenseBufferRegionSource`), surfaces by a
fresh `SurfaceAssigner`. The recorded region and surface events are not
replayed, so tuning that logic needs only a replay, never a new flight.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from surmap.demo.events import DemoEvent, RegionPlacer, SurfaceAssigner
from surmap.demo.history import RunHistoryStore
from surmap.demo.surface_render import SurfaceLayer
from surmap.slam.dense import DenseBufferRegionSource, region_rig_from_message
from surmap.survey.surfaces import SurfaceMap

Bounds = tuple[NDArray[np.float32], NDArray[np.float32]]
# Draws the 3D view of (points, colours, bounds, surface layer) as PNG base64.
CloudRenderer = Callable[[NDArray[np.float32], NDArray[np.uint8], Bounds, SurfaceLayer], str]


class ReplayControls(Protocol):
    """What a replay obeys: pause and cancel (the demo's `PlaybackControls` fits)."""

    @property
    def paused(self) -> bool: ...
    @property
    def cancelled(self) -> bool: ...
    def wait_while_paused(self, timeout: float) -> None: ...


class _Unattended:
    """Controls of a replay nobody steers: never paused, never cancelled."""

    paused = False
    cancelled = False

    def wait_while_paused(self, timeout: float) -> None:
        pass


class JournalPlayer:
    """Plays one journalled run as demo events, re-running regions and surfaces.

    `fps` paces frames (0: as fast as possible). `surfaces` is the
    surface logic under test (default: a fresh `SurfaceMap`).
    `render_cloud`, when given, redraws each map view with the replay's
    surfaces; without it the views are left out.
    """

    def __init__(
        self,
        store: RunHistoryStore,
        run_id: str,
        *,
        controls: ReplayControls | None = None,
        fps: float = 0.0,
        surfaces: SurfaceMap | None = None,
        render_cloud: CloudRenderer | None = None,
    ) -> None:
        if fps < 0:
            raise ValueError("fps must not be negative")
        self._store = store
        self._run_id = run_id
        self._controls: ReplayControls = controls if controls is not None else _Unattended()
        self._fps = fps
        self._assigner = SurfaceAssigner(surfaces)
        self._render_cloud = render_cloud
        self._bounds: Bounds | None = None

    def _placer(self) -> RegionPlacer | None:
        """Regions answered from the dense buffer of the run this one replays."""
        root = self._store.root_run(self._run_id)
        journalled = self._store.rig(root)
        if journalled is None:
            return None
        size = journalled["display_size"]
        assert isinstance(size, list) and len(size) == 2
        source = DenseBufferRegionSource(
            region_rig_from_message(journalled["rig"]), self._store.dense_frames(root)
        )
        return RegionPlacer(source, (int(size[0]), int(size[1])))

    def _view(self, data: dict[str, object]) -> dict[str, object]:
        """A map/final event's data with its 3D view drawn from the replay's surfaces."""
        points_raw, colors_raw = data.get("points"), data.get("point_colors")
        if self._render_cloud is None or not isinstance(points_raw, list) or not points_raw:
            return data
        points = np.array(points_raw, np.float32).reshape(-1, 3)
        colors = np.array(colors_raw or [], np.uint8).reshape(-1, 3)
        if len(colors) != len(points):
            colors = np.full((len(points), 3), 160, np.uint8)
        lo, hi = points.min(axis=0), points.max(axis=0)
        if self._bounds is not None:
            lo, hi = np.minimum(self._bounds[0], lo), np.maximum(self._bounds[1], hi)
        self._bounds = (lo, hi)
        png = self._render_cloud(points, colors, self._bounds, self._assigner.layer())
        return {**data, "cloud_png": png}

    def _pace(self, last_frame: float) -> float:
        if self._fps > 0:
            remaining = 1.0 / self._fps - (time.monotonic() - last_frame)
            if remaining > 0:
                time.sleep(remaining)
        return time.monotonic()

    def events(self) -> Iterator[DemoEvent]:
        store, run_id = self._store, self._run_id
        placer = self._placer()
        yield DemoEvent(
            "status",
            {"message": f"Replaying run {run_id[:8]} from its journal (no RTAB-Map, no SAM)"},
        )
        last_frame = 0.0
        for kind, data in store.journal(run_id):
            while self._controls.paused and not self._controls.cancelled:
                self._controls.wait_while_paused(0.05)
            if self._controls.cancelled:
                return
            if kind in ("region", "surface"):
                continue  # computed again below, from the dense buffer
            if kind == "frame":
                last_frame = self._pace(last_frame)
                jpeg = store.frame_jpeg(run_id, int(str(data["frame_id"]))) or b""
                yield DemoEvent("frame", data, jpeg=jpeg)
            elif kind in ("map", "final"):
                yield DemoEvent(kind, self._view(data))
            elif kind == "sam":
                jpeg = store.frame_jpeg(run_id, int(str(data["frame_id"]))) or b""
                sam = DemoEvent("sam", data, jpeg=jpeg)
                yield sam
                if placer is not None:
                    region = placer.region_event(sam)
                    yield region
                    if (surface := self._assigner.surface_event(region)) is not None:
                        yield surface
            else:
                yield DemoEvent(kind, data)
