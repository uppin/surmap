"""Demo events: what the player streams, and the SAM / region / surface events among them.

A `sam` event carries one SAM result (masks keyed by `frame_id`); with a
live map that can answer regions, a `region` event follows it carrying
each mask's dense map-frame points from that one frame, and a `surface`
event follows that: the station's assignment of those points to
persistent object surfaces (`surmap.survey.surfaces`), which the 3D pane
draws as its surface layer.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from surmap.demo.surface_render import SurfaceLayer
from surmap.slam.regions import RegionPointSource, RegionQuery
from surmap.slam.sidecar import SidecarError
from surmap.survey.sam import SamDetection
from surmap.survey.surfaces import SurfaceMap

# Cap on one region event's points for the browser (evenly sampled).
MAX_REGION_POINTS = 50_000

# How long a SAM region may wait for the sidecar's dense stereo.
REGION_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class DemoEvent:
    kind: str  # frame | status | final | map | detections | sam | region | surface
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
                    "score": round(detection.score, 2),
                    "track_id": detection.track_id,
                    "box": [round(value, 1) for value in detection.box_xyxy],
                    "mask_polygon": [[round(x, 1), round(y, 1)] for x, y in detection.mask_polygon],
                }
                for detection in detections
            ],
        },
    )


class RegionPlacer:
    """Turns a released `sam` event into its `region` event (left channel, display px)."""

    def __init__(self, source: RegionPointSource, size: tuple[int, int]) -> None:
        self._source = source
        self._size = size
        self._next_query = 1

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
            points = result.points
            if len(points) > MAX_REGION_POINTS:
                step = len(points) / MAX_REGION_POINTS
                points = tuple(points[int(i * step)] for i in range(MAX_REGION_POINTS))
            regions.append(
                {
                    "track_id": obj["track_id"],
                    "label": obj["label"],
                    "status": result.status.value,
                    "points": [[round(p.x, 3), round(p.y, 3), round(p.z, 3)] for p in points],
                }
            )
        return DemoEvent("region", {"frame_id": frame_id, "regions": regions})


def _rounded(points: NDArray[np.float32]) -> list[list[float]]:
    rounded: list[list[float]] = np.round(points.astype(np.float64), 3).tolist()
    return rounded


class SurfaceAssigner:
    """Turns a `region` event into its `surface` event; owns the run's surfaces."""

    def __init__(self, surfaces: SurfaceMap | None = None) -> None:
        self._surfaces = surfaces if surfaces is not None else SurfaceMap()

    @property
    def version(self) -> int:
        return self._surfaces.version

    def layer(self) -> SurfaceLayer:
        return tuple(
            (surface.surface_id, surface.points, surface.moving)
            for surface in self._surfaces.surfaces()
        )

    def surface_event(self, region: DemoEvent) -> DemoEvent | None:
        """None when no region of the event placed any point."""
        frame_id = int(str(region.data["frame_id"]))
        regions = region.data["regions"]
        assert isinstance(regions, list)
        assigned: list[dict[str, object]] = []
        for placed in regions:
            points = np.array(placed["points"], dtype=np.float32).reshape(-1, 3)
            track_id = int(placed["track_id"])
            assignment = self._surfaces.assign(frame_id, track_id, str(placed["label"]), points)
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
