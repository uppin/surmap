"""Demo events: what the player streams, and the SAM / region events among them.

A `sam` event carries one SAM result (masks keyed by `frame_id`); with a
live map that can answer regions, a `region` event follows it carrying
each mask's dense map-frame points from that one frame — the 3D pane
replaces its region layer with it, never accumulating.
"""

from __future__ import annotations

from dataclasses import dataclass

from surmap.slam.regions import RegionPointSource, RegionQuery
from surmap.slam.sidecar import SidecarError
from surmap.survey.sam import SamDetection

# Cap on one region event's points for the browser (evenly sampled).
MAX_REGION_POINTS = 50_000

# How long a SAM region may wait for the sidecar's dense stereo.
REGION_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class DemoEvent:
    kind: str  # "frame" | "status" | "final" | "map" | "detections" | "sam" | "region"
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
