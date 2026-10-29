"""PX4 SITL / Gazebo capture directory as viewer ticks.

The directory is the one PR #18 writes: `calibration.json`,
`frames.jsonl`, optional `gps.csv`, and `images/`. This module does
not import that branch. The vehicle position is GPS converted to the
snapshot's east/north/up frame. SurMap does not command the vehicle.
"""

from __future__ import annotations

import io
import json
import math
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from surmap.types import Vec3
from surmap.viewer.model import (
    CameraModel,
    ViewerTick,
    empty_snapshot,
    hud_badges,
)
from surmap.viewer.poses import camera_pose, enu_offset
from surmap.viewer.project import track_overlays
from surmap.viewer.snapshot import read_snapshot
from surmap.viewer.timeline import placed_tracks


@dataclass(frozen=True)
class _Frame:
    t_ns: int
    left: Path
    right: Path | None


@dataclass(frozen=True)
class _Fix:
    t_ns: int
    lat: float
    lon: float
    alt: float


class SitlReplay:
    """One capture directory."""

    def __init__(
        self,
        capture: Path,
        *,
        snapshot_path: Path | None = None,
        max_frames: int = 0,
        max_width: int = 640,
        pitch_down_rad: float = 0.45,
    ) -> None:
        self.title = capture.name
        self.source_name = "sitl"
        self.snapshot_path = str(snapshot_path) if snapshot_path is not None else None
        self.snapshot = (
            read_snapshot(snapshot_path) if snapshot_path is not None else empty_snapshot()
        )
        self._capture = capture
        self._camera = _calibration(capture / "calibration.json")
        self._frames = _frames(capture)
        if max_frames > 0:
            self._frames = self._frames[:max_frames]
        self._fixes = _fixes(capture / "gps.csv")
        self._max_width = max_width
        self._pitch = pitch_down_rad

    def ticks(self) -> Iterator[ViewerTick]:
        frames = self._frames
        total = len(frames)
        if total == 0:
            return
        replay_start = frames[0].t_ns
        replay_end = frames[-1].t_ns
        origin = self._fixes[0] if self._fixes else None
        for index, frame in enumerate(frames):
            jpeg, width, height, camera = _image(frame.left, self._camera, self._max_width)
            position, gps_fix = _position(self._fixes, frame.t_ns, origin)
            yaw = _yaw(self._fixes, frame.t_ns)
            pose = camera_pose(position, yaw, self._pitch)
            placed = placed_tracks(
                self.snapshot, frame.t_ns, replay_start=replay_start, replay_end=replay_end
            )
            visible = sum(1 for item in placed if item.visible)
            yield ViewerTick(
                index=index,
                total=total,
                t_ns=frame.t_ns,
                jpeg=jpeg,
                width=width,
                height=height,
                drone=position,
                points=(),
                scene_points=0,
                overlays=track_overlays(pose, placed, camera),
                placed=placed,
                height_m=position.z,
                gps_fix=gps_fix,
                pose_ok=gps_fix,
                hud=hud_badges(
                    mapping=False,
                    landmark_count=visible,
                    gps_fix=gps_fix,
                    pose_ok=gps_fix,
                ),
            )


def _calibration(path: Path) -> CameraModel:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a JSON object")
    fields = {str(key): value for key, value in raw.items()}

    def number(name: str) -> float:
        value = fields.get(name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{path} field {name} must be a number")
        return float(value)

    return CameraModel(
        fx=number("fx"),
        fy=number("fy"),
        cx=number("cx"),
        cy=number("cy"),
        width=int(number("width")),
        height=int(number("height")),
    )


def _frames(capture: Path) -> tuple[_Frame, ...]:
    path = capture / "frames.jsonl"
    frames = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        raw = json.loads(stripped)
        if not isinstance(raw, dict):
            raise ValueError(f"{path}:{line_number} is not an object")
        fields = {str(key): value for key, value in raw.items()}
        t_ns = fields.get("t_ns")
        left = fields.get("left")
        if isinstance(t_ns, bool) or not isinstance(t_ns, int):
            raise ValueError(f"{path}:{line_number} t_ns must be an integer")
        if not isinstance(left, str):
            raise ValueError(f"{path}:{line_number} left must be a path")
        right = fields.get("right")
        right_path = capture / right if isinstance(right, str) else None
        frames.append(_Frame(t_ns, capture / left, right_path))
    return tuple(frames)


def _fixes(path: Path) -> tuple[_Fix, ...]:
    if not path.is_file():
        return ()
    fixes = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("t_ns"):
            continue
        parts = [part.strip() for part in stripped.split(",")]
        if len(parts) < 4:
            raise ValueError(f"{path}:{line_number + 1} needs t_ns,lat,lon,alt")
        fixes.append(_Fix(int(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])))
    return tuple(fixes)


def _position(fixes: tuple[_Fix, ...], t_ns: int, origin: _Fix | None) -> tuple[Vec3, bool]:
    if origin is None or not fixes:
        return Vec3(0.0, 0.0, 0.0), False
    fix = min(fixes, key=lambda item: abs(item.t_ns - t_ns))
    return (
        enu_offset(origin.lat, origin.lon, origin.alt, fix.lat, fix.lon, fix.alt),
        True,
    )


def _yaw(fixes: tuple[_Fix, ...], t_ns: int) -> float:
    if len(fixes) < 2:
        return 0.0
    index = min(range(len(fixes)), key=lambda item: abs(fixes[item].t_ns - t_ns))
    nxt = fixes[min(index + 1, len(fixes) - 1)]
    prev = fixes[max(index - 1, 0)]
    if nxt.t_ns == prev.t_ns:
        return 0.0
    origin = fixes[0]
    start = enu_offset(origin.lat, origin.lon, origin.alt, prev.lat, prev.lon, prev.alt)
    end = enu_offset(origin.lat, origin.lon, origin.alt, nxt.lat, nxt.lon, nxt.alt)
    return math.atan2(end.x - start.x, end.y - start.y)


def _image(
    path: Path, calibration: CameraModel, max_width: int
) -> tuple[bytes, int, int, CameraModel]:
    with Image.open(path) as image:
        frame = image.convert("RGB")
        width, height = frame.width, frame.height
        if width > max_width:
            height = max(1, round(frame.height * max_width / width))
            width = max_width
            frame = frame.resize((width, height), Image.Resampling.BILINEAR)
        scale_x = width / calibration.width
        scale_y = height / calibration.height
        scaled = CameraModel(
            fx=calibration.fx * scale_x,
            fy=calibration.fy * scale_y,
            cx=calibration.cx * scale_x,
            cy=calibration.cy * scale_y,
            width=width,
            height=height,
        )
        buffer = io.BytesIO()
        frame.save(buffer, format="JPEG", quality=82)
        return buffer.getvalue(), width, height, scaled
