"""Synthetic survey replay.

Same viewer clock as EuRoC and SITL, with a bundled v1 snapshot so the
panes can be opened without downloading a dataset. The camera is a
projection of the same ground the point cloud uses.
"""

from __future__ import annotations

import io
import math
from collections.abc import Iterator
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from surmap.types import Pose, Vec3
from surmap.viewer.model import CameraModel, PlacedTrack, ViewerTick, hud_badges
from surmap.viewer.poses import camera_pose
from surmap.viewer.project import track_overlays
from surmap.viewer.snapshot import read_snapshot
from surmap.viewer.timeline import placed_tracks

_WIDTH = 640
_HEIGHT = 360
_CAMERA = CameraModel(fx=520.0, fy=520.0, cx=320.0, cy=180.0, width=_WIDTH, height=_HEIGHT)
_STEP_NS = 100_000_000
_START_NS = 1_000_000_000


def bundled_snapshot_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "semantic_map_snapshot.json"


class PreviewReplay:
    """A scripted pass over the bundled snapshot."""

    def __init__(self, *, frames: int = 72, snapshot_path: Path | None = None) -> None:
        path = snapshot_path if snapshot_path is not None else bundled_snapshot_path()
        self.title = "Preview survey"
        self.source_name = "preview"
        self.snapshot_path: str | None = str(path)
        self.snapshot = read_snapshot(path)
        self._frames = frames

    def ticks(self) -> Iterator[ViewerTick]:
        total = self._frames
        if total <= 0:
            return
        replay_start = _START_NS
        replay_end = _START_NS + (total - 1) * _STEP_NS
        seen: set[tuple[int, int, int]] = set()
        mapped = False
        field = _terrain_points()
        for index in range(total):
            t_ns = _START_NS + index * _STEP_NS
            progress = 0.0 if total == 1 else index / (total - 1)
            position = Vec3(
                -5.0 + 12.0 * progress,
                -1.0 + 12.0 * progress,
                5.5 + 0.6 * math.sin(progress * math.pi),
            )
            yaw = math.atan2(12.0, 12.0)
            pose = camera_pose(position, yaw, 0.52)
            placed = placed_tracks(
                self.snapshot, t_ns, replay_start=replay_start, replay_end=replay_end
            )
            fresh = _near(field, position, seen)
            if fresh:
                mapped = True
            visible = sum(1 for item in placed if item.visible)
            jpeg = _render(pose, placed)
            yield ViewerTick(
                index=index,
                total=total,
                t_ns=t_ns,
                jpeg=jpeg,
                width=_WIDTH,
                height=_HEIGHT,
                drone=position,
                points=fresh,
                scene_points=len(fresh),
                overlays=track_overlays(pose, placed, _CAMERA),
                placed=placed,
                height_m=position.z,
                gps_fix=self.snapshot.origin is not None,
                pose_ok=True,
                hud=hud_badges(
                    mapping=mapped,
                    landmark_count=visible,
                    gps_fix=self.snapshot.origin is not None,
                    pose_ok=True,
                ),
            )


def terrain(x: float, y: float) -> float:
    """Height of the preview ground, metres. Matches the camera render."""
    mound = 2.4 * math.exp(-((x - 3.0) ** 2 + (y - 6.0) ** 2) / 16.0)
    ridge = 1.1 * math.exp(-((x - 7.0) ** 2) / 4.0) * math.exp(-((y - 10.0) ** 2) / 10.0)
    ripple = 0.12 * math.sin(x * 0.7) * math.cos(y * 0.45)
    return max(0.0, mound + ridge + ripple)


def _terrain_points() -> tuple[Vec3, ...]:
    points: list[Vec3] = []
    for x in _frange(-8.0, 12.0, 0.55):
        for y in _frange(-4.0, 16.0, 0.55):
            points.append(Vec3(x, y, terrain(x, y)))
    return tuple(points)


def _frange(start: float, stop: float, step: float) -> tuple[float, ...]:
    values = []
    value = start
    while value <= stop + 1e-9:
        values.append(value)
        value += step
    return tuple(values)


def _near(
    field: tuple[Vec3, ...], drone: Vec3, seen: set[tuple[int, int, int]]
) -> tuple[Vec3, ...]:
    fresh: list[Vec3] = []
    for point in field:
        if (point.x - drone.x) ** 2 + (point.y - drone.y) ** 2 > 13.0**2:
            continue
        key = (round(point.x / 0.55), round(point.y / 0.55), round(point.z / 0.4))
        if key in seen:
            continue
        seen.add(key)
        fresh.append(point)
        if len(fresh) >= 240:
            break
    return tuple(fresh)


def _render(pose: Pose, placed: tuple[PlacedTrack, ...]) -> bytes:
    from surmap.geometry import to_map_frame

    camera = _CAMERA
    ys, xs = np.mgrid[0 : camera.height, 0 : camera.width]
    dx = (xs.astype(np.float32) - camera.cx) / camera.fx
    dy = (ys.astype(np.float32) - camera.cy) / camera.fy
    right = to_map_frame(Vec3(1.0, 0.0, 0.0), Pose(Vec3(0.0, 0.0, 0.0), pose.orientation_xyzw))
    down = to_map_frame(Vec3(0.0, 1.0, 0.0), Pose(Vec3(0.0, 0.0, 0.0), pose.orientation_xyzw))
    forward = to_map_frame(Vec3(0.0, 0.0, 1.0), Pose(Vec3(0.0, 0.0, 0.0), pose.orientation_xyzw))
    dir_x = right.x * dx + down.x * dy + forward.x
    dir_y = right.y * dx + down.y * dy + forward.y
    dir_z = right.z * dx + down.z * dy + forward.z
    with np.errstate(divide="ignore", invalid="ignore"):
        travel = np.where(dir_z < -1e-3, (0.0 - pose.position.z) / dir_z, np.nan)
    travel = np.where(travel > 0.0, travel, np.nan)
    hit_x = pose.position.x + travel * dir_x
    hit_y = pose.position.y + travel * dir_y
    finite = np.isfinite(travel)
    height = np.where(
        finite, _terrain_array(np.where(finite, hit_x, 0.0), np.where(finite, hit_y, 0.0)), 0.0
    )
    shade = np.clip(height / 3.2, 0.0, 1.0)
    grid = (np.abs(np.mod(hit_x, 2.0)) < 0.07) | (np.abs(np.mod(hit_y, 2.0)) < 0.07)
    fog = np.clip(np.nan_to_num(travel, nan=40.0) / 42.0, 0.0, 1.0)
    sky = ~finite
    row = ys.astype(np.float32) / camera.height
    red = np.where(sky, 22.0 + row * 20.0, 70.0 + shade * 90.0 - grid * 16.0)
    green = np.where(sky, 28.0 + row * 22.0, 74.0 + shade * 55.0 - grid * 12.0)
    blue = np.where(sky, 38.0 + row * 14.0, 58.0 + shade * 28.0 - grid * 10.0)
    red = red * (1.0 - fog) + 18.0 * fog
    green = green * (1.0 - fog) + 24.0 * fog
    blue = blue * (1.0 - fog) + 32.0 * fog
    pixels = np.stack([red, green, blue], axis=-1).clip(0, 255).astype(np.uint8)
    image = Image.fromarray(pixels, mode="RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    for overlay in track_overlays(pose, placed, camera):
        if len(overlay.mask) >= 3:
            draw.polygon(list(overlay.mask), fill=(28, 26, 24, 170))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


def _terrain_array(x: NDArray[np.float32], y: NDArray[np.float32]) -> NDArray[np.float32]:
    mound = 2.4 * np.exp(-((x - 3.0) ** 2 + (y - 6.0) ** 2) / 16.0)
    ridge = 1.1 * np.exp(-((x - 7.0) ** 2) / 4.0) * np.exp(-((y - 10.0) ** 2) / 10.0)
    ripple = 0.12 * np.sin(x * 0.7) * np.cos(y * 0.45)
    return np.asarray(np.maximum(0.0, mound + ridge + ripple), dtype=np.float32)
