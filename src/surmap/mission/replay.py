"""One viewer clock for a mission snapshot. No Gazebo window."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

from PIL import Image

from surmap.types import Vec3
from surmap.viewer.model import PlacedTrack, ViewerTick, hud_badges
from surmap.viewer.snapshot import read_snapshot

_WIDTH = 64
_HEIGHT = 48


class MissionReplay:
    """Shows the mission landmarks. The camera frame is a blank JPEG."""

    def __init__(self, snapshot_path: Path) -> None:
        self.title = "Disaster mission"
        self.source_name = "mission-demo"
        self.snapshot_path: str | None = str(snapshot_path)
        self.snapshot = read_snapshot(snapshot_path)

    def ticks(self) -> Iterator[ViewerTick]:
        tracks = self.snapshot.tracks()
        points: list[Vec3] = []
        for track in tracks:
            if track.mask_points:
                points.extend(track.mask_points)
            else:
                points.append(track.xyz)
        last_t = max((track.t_ns for track in tracks), default=0)
        drone = points[0] if points else Vec3(0.0, 0.0, 0.0)
        gps_fix = self.snapshot.origin is not None
        yield ViewerTick(
            index=0,
            total=1,
            t_ns=last_t,
            jpeg=_blank_jpeg(),
            width=_WIDTH,
            height=_HEIGHT,
            drone=drone,
            points=tuple(points),
            scene_points=len(points),
            overlays=(),
            placed=tuple(PlacedTrack(track, track.xyz, (track.xyz,), True) for track in tracks),
            height_m=drone.z,
            gps_fix=gps_fix,
            pose_ok=True,
            hud=hud_badges(
                mapping=bool(points),
                landmark_count=len(self.snapshot.landmarks),
                gps_fix=gps_fix,
                pose_ok=True,
            ),
        )


def _blank_jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (_WIDTH, _HEIGHT), (24, 28, 34)).save(buffer, format="JPEG")
    return buffer.getvalue()
