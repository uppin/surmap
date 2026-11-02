"""Demo events: what the player streams, and the SAM / region / surface events among them.

A `sam` event carries one SAM result (masks keyed by `frame_id`); with a
live map that can answer regions, a `region` event follows it carrying
each mask's dense map-frame points from that one frame — with the camera
position they were placed from (`viewpoint`) and, when the source knows
its rig, the object's own points (`object_points`) as `[u, v, range_m]`
on the SAM image (`pixels`) — and a `surface`
event follows that: the station's assignment of those points to
persistent object surfaces (`surmap.survey.surfaces`), which the 3D pane
draws as its surface layer.

`rig` and `dense` events carry RTAB-Map's dense buffer into the run's
journal (`RunHistoryStore`) and never reach a viewer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from surmap.demo.surface_render import SurfaceLayer
from surmap.slam.dense import DenseFrame, RegionRig, project_to_display
from surmap.slam.regions import RegionPointSource, RegionQuery, RegionResult
from surmap.slam.sidecar import SidecarError
from surmap.survey.sam import SamDetection
from surmap.survey.surfaces import (
    DEFAULT_DEPTH_BAND_M,
    DENSE_REGION_MIN_POINTS,
    SurfaceMap,
    object_points,
)
from surmap.types import Pose, Vec3

# Cap on one region event's points for the browser (evenly sampled).
MAX_REGION_POINTS = 50_000

# Cap on one region's SAM-pane pixels (evenly sampled).
MAX_REGION_PIXELS = 1500

# How long a SAM region may wait for the sidecar's dense stereo.
REGION_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class DemoEvent:
    # frame | status | final | map | detections | sam | region | surface,
    # and the journal-only rig | dense
    kind: str
    data: dict[str, object]
    jpeg: bytes = b""


def sam_event(frame_id: int, t_ns: int, detections: tuple[SamDetection, ...]) -> DemoEvent:
    # A separate event, keyed by frame_id like `detections` — the page
    # joins SAM masks to the frame on screen by frame_id.
    return DemoEvent(
        "sam",
        {
            "frame_id": frame_id,
            "t_ns": t_ns,
            "objects": [
                {
                    "label": detection.label,
                    "score": None if detection.score is None else round(detection.score, 2),
                    "track_id": detection.track_id,
                    "box": [round(value, 1) for value in detection.box_xyxy],
                    "mask_polygon": [[round(x, 1), round(y, 1)] for x, y in detection.mask_polygon],
                }
                for detection in detections
            ],
        },
    )


# Event kinds recorded into the journal but never published to viewers.
JOURNAL_ONLY = ("rig", "dense")


def rig_event(rig: RegionRig, size: tuple[int, int]) -> DemoEvent:
    """The rig regions are answered with, and the display size they are asked at."""
    return DemoEvent("rig", {"rig": rig.as_message(), "display_size": list(size)})


def dense_event(frame: DenseFrame) -> DemoEvent:
    """One journalled dense frame; the disparity PNG rides as the event's bytes."""
    position = frame.to_map.position
    return DemoEvent(
        "dense",
        {
            "frame_id": frame.frame_id,
            "t_ns": frame.t_ns,
            "channel": frame.channel,
            "to_map": [position.x, position.y, position.z, *frame.to_map.orientation_xyzw],
        },
        jpeg=frame.disparity_png,
    )


def dense_frame_of(event: DemoEvent) -> DenseFrame:
    to_map = event.data["to_map"]
    assert isinstance(to_map, list) and len(to_map) == 7
    x, y, z, qx, qy, qz, qw = (float(value) for value in to_map)
    return DenseFrame(
        int(str(event.data["frame_id"])),
        int(str(event.data["t_ns"])),
        int(str(event.data["channel"])),
        Pose(Vec3(x, y, z), (qx, qy, qz, qw)),
        event.jpeg,
    )


@runtime_checkable
class RiggedRegionSource(Protocol):
    """A region source that knows the rig it answers with (sidecar v5, a dense buffer)."""

    @property
    def region_rig(self) -> RegionRig | None: ...


def _sampled(count: int, cap: int) -> NDArray[np.int64]:
    if count <= cap:
        return np.arange(count)
    indices: NDArray[np.int64] = (np.arange(cap) * (count / cap)).astype(np.int64)
    return indices


class RegionPlacer:
    """Turns a released `sam` event into its `region` event (left channel, display px)."""

    def __init__(
        self,
        source: RegionPointSource,
        size: tuple[int, int],
        depth_band_m: float = DEFAULT_DEPTH_BAND_M,
    ) -> None:
        self._source = source
        self._size = size
        self._depth_band_m = depth_band_m
        self._next_query = 1

    def _pixels(self, result: RegionResult, points: NDArray[np.float64]) -> list[list[float]]:
        """The object's own points as `[u, v, range_m]` on the display image."""
        rig = self._source.region_rig if isinstance(self._source, RiggedRegionSource) else None
        camera = result.camera
        if rig is None or camera is None or not len(points):
            return []
        viewpoint = camera.position
        kept = object_points(points.astype(np.float32), viewpoint, self._depth_band_m)
        kept = kept[_sampled(len(kept), MAX_REGION_PIXELS)].astype(np.float64)
        uv = project_to_display(kept, camera, rig, result.channel, self._size)
        ranges = np.linalg.norm(kept - (viewpoint.x, viewpoint.y, viewpoint.z), axis=1)
        drawn = np.column_stack([uv, ranges])
        drawn = drawn[np.isfinite(drawn).all(axis=1)]
        pixels: list[list[float]] = np.round(drawn, 3).tolist()
        return pixels

    def region_event(self, sam: DemoEvent) -> DemoEvent:
        frame_id = int(str(sam.data["frame_id"]))
        objects = sam.data["objects"]
        assert isinstance(objects, list)
        regions: list[dict[str, object]] = []
        for obj in objects:
            query = RegionQuery(
                query_id=self._next_query,
                frame_id=frame_id,
                channel=0,
                width=self._size[0],
                height=self._size[1],
                polygon=tuple((float(x), float(y)) for x, y in obj["mask_polygon"]),
            )
            self._next_query += 1
            try:
                result = self._source.region_points(query, timeout=REGION_TIMEOUT_S)
            except SidecarError:
                continue  # a region that never came back is not drawn
            every = np.array([(p.x, p.y, p.z) for p in result.points], np.float64).reshape(-1, 3)
            xyz = every[_sampled(len(every), MAX_REGION_POINTS)]
            camera = result.camera
            regions.append(
                {
                    "track_id": obj["track_id"],
                    "label": obj["label"],
                    "status": result.status.value,
                    "points": np.round(xyz, 3).tolist(),
                    "viewpoint": (
                        None
                        if camera is None
                        else [camera.position.x, camera.position.y, camera.position.z]
                    ),
                    "pixels": self._pixels(result, every),
                }
            )
        return DemoEvent("region", {"frame_id": frame_id, "regions": regions})


def _rounded(points: NDArray[np.float32]) -> list[list[float]]:
    rounded: list[list[float]] = np.round(points.astype(np.float64), 3).tolist()
    return rounded


class SurfaceAssigner:
    """Turns a `region` event into its `surface` event; owns the run's surfaces.

    Regions are dense, so by default a mask needs `DENSE_REGION_MIN_POINTS`
    of its own points to start or continue a surface.
    """

    def __init__(self, surfaces: SurfaceMap | None = None) -> None:
        self._surfaces = (
            surfaces if surfaces is not None else SurfaceMap(min_points=DENSE_REGION_MIN_POINTS)
        )

    @property
    def version(self) -> int:
        return self._surfaces.version

    def layer(self) -> SurfaceLayer:
        return tuple(
            (surface.surface_id, surface.points, surface.moving)
            for surface in self._surfaces.surfaces()
        )

    def surface_event(self, region: DemoEvent) -> DemoEvent | None:
        """None when no region of the event placed enough points (see `SurfaceMap`)."""
        frame_id = int(str(region.data["frame_id"]))
        regions = region.data["regions"]
        assert isinstance(regions, list)
        assigned: list[dict[str, object]] = []
        for placed in regions:
            points = np.array(placed["points"], dtype=np.float32).reshape(-1, 3)
            track_id = int(placed["track_id"])
            seen_from = placed.get("viewpoint")
            viewpoint = (
                Vec3(*(float(v) for v in seen_from)) if isinstance(seen_from, list) else None
            )
            assignment = self._surfaces.assign(
                frame_id, track_id, str(placed["label"]), points, viewpoint
            )
            if assignment is None:
                continue
            assigned.append(
                {
                    "surface_id": assignment.surface_id,
                    "label": assignment.label,
                    "track_id": assignment.track_id,
                    "continued": assignment.continued,
                    "points": _rounded(assignment.points),
                    "total_points": assignment.total_points,
                    "moving": assignment.moving,
                }
            )
        return (
            DemoEvent("surface", {"frame_id": frame_id, "surfaces": assigned}) if assigned else None
        )


def surface_layer(surfaces: object) -> SurfaceLayer:
    """The drawable layer of persisted surfaces (`RunHistoryStore.surfaces_at`)."""
    layer: list[tuple[int, NDArray[np.float32], bool]] = []
    for surface in surfaces if isinstance(surfaces, list) else []:
        if isinstance(surface, dict) and isinstance(surface.get("points"), list):
            points = np.array(surface["points"], dtype=np.float32).reshape(-1, 3)
            layer.append((int(surface["surface_id"]), points, bool(surface.get("moving"))))
    return tuple(layer)
