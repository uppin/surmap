"""EuRoC replay as viewer ticks.

The drone pose is the dataset ground-truth body pose. Scene points are
the stereo cloud in that map frame. RTAB-Map is not required. A semantic
map snapshot is optional and is not invented for the sequence.
"""

from __future__ import annotations

import bisect
import io
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from surmap.demo.datasets import PreparedDataset, load_calibration
from surmap.detection.source import DetectionSource
from surmap.detection.tracker import TrackedDetection
from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from surmap.types import Pose, Vec3
from surmap.viewer.model import (
    CameraModel,
    ViewerTick,
    empty_snapshot,
    hud_badges,
)
from surmap.viewer.poses import compose_camera_pose
from surmap.viewer.project import detection_overlays, map_points, track_overlays
from surmap.viewer.snapshot import read_snapshot
from surmap.viewer.timeline import placed_tracks

_SCENE_LIMIT = 180


@dataclass(frozen=True)
class _GroundTruth:
    t_ns: int
    pose: Pose


class EurocReplay:
    """One prepared EuRoC dataset, played as viewer ticks."""

    def __init__(
        self,
        prepared: PreparedDataset,
        *,
        snapshot_path: Path | None = None,
        fps_hint: float = 8.0,
        max_frames: int = 0,
        start_index: int = 0,
        max_width: int = 376,
        stereo: bool = True,
        detections: DetectionSource | None = None,
    ) -> None:
        del fps_hint
        self.title = prepared.spec.title
        self.source_name = "euroc"
        self.snapshot_path = str(snapshot_path) if snapshot_path is not None else None
        self.snapshot = (
            read_snapshot(snapshot_path) if snapshot_path is not None else empty_snapshot()
        )
        self._prepared = prepared
        self._max_frames = max_frames
        self._start_index = start_index
        self._max_width = max_width
        self._stereo_enabled = stereo
        self._stereo = StereoReconstructor(max_points=1200, stride=3, match_width_px=160)
        self._detections = detections
        self._groundtruth = _load_groundtruth(prepared)
        self._body_rotation, self._body_translation = _t_bs(prepared.sensor_yaml("cam0"))

    def ticks(self) -> Iterator[ViewerTick]:
        timestamps = self._prepared.timestamps_ns[self._start_index :]
        if self._max_frames > 0:
            timestamps = timestamps[: self._max_frames]
        total = len(timestamps)
        if total == 0:
            return
        replay_start = timestamps[0]
        replay_end = timestamps[-1]
        mapped = False
        native = load_calibration(self._prepared)
        for index, t_ns in enumerate(timestamps):
            jpeg, width, height = _jpeg(self._prepared.frame_path(0, t_ns), self._max_width)
            scale_x = width / native.width
            scale_y = height / native.height
            camera = CameraModel(
                fx=native.fx * scale_x,
                fy=native.fy * scale_y,
                cx=native.cx * scale_x,
                cy=native.cy * scale_y,
                width=width,
                height=height,
            )
            body, pose_ok = _body_pose(self._groundtruth, t_ns)
            camera_pose = compose_camera_pose(body, self._body_rotation, self._body_translation)
            camera_cloud = self._scene_points(t_ns, jpeg, width, height, camera, native.baseline_m)
            scene_count = len(camera_cloud)
            if scene_count:
                mapped = True
            placed = placed_tracks(
                self.snapshot, t_ns, replay_start=replay_start, replay_end=replay_end
            )
            found = self._detect(index, jpeg, width, height)
            overlays = track_overlays(camera_pose, placed, camera) + detection_overlays(
                camera_pose, found, camera_cloud, camera
            )
            visible = sum(1 for item in placed if item.visible)
            yield ViewerTick(
                index=index,
                total=total,
                t_ns=t_ns,
                jpeg=jpeg,
                width=width,
                height=height,
                drone=body.position,
                points=map_points(camera_pose, camera_cloud, _SCENE_LIMIT),
                scene_points=scene_count,
                overlays=overlays,
                placed=placed,
                height_m=body.position.z,
                gps_fix=False,
                pose_ok=pose_ok,
                hud=hud_badges(
                    mapping=mapped,
                    landmark_count=visible,
                    gps_fix=False,
                    pose_ok=pose_ok,
                ),
            )

    def _scene_points(
        self,
        t_ns: int,
        left_jpeg: bytes,
        width: int,
        height: int,
        camera: CameraModel,
        baseline_m: float,
    ) -> tuple[Vec3, ...]:
        if not self._stereo_enabled:
            return ()
        right_path = self._prepared.frame_path(1, t_ns)
        if not right_path.is_file():
            return ()
        right_jpeg, _right_w, _right_h = _jpeg(right_path, self._max_width)
        rig = StereoRig(camera.fx, camera.fy, camera.cx, camera.cy, baseline_m)
        return self._stereo.reconstruct(
            FrameImage(width, height, "mjpeg", left_jpeg),
            FrameImage(width, height, "mjpeg", right_jpeg),
            rig,
        )

    def _detect(
        self, index: int, jpeg: bytes, width: int, height: int
    ) -> tuple[TrackedDetection, ...]:
        if self._detections is None:
            return ()
        from surmap.detection.detector import decode_rgb

        rgb = decode_rgb(FrameImage(width, height, "mjpeg", jpeg))
        return self._detections.detect_tracked(index + 1, rgb)


def _jpeg(path: Path, max_width: int) -> tuple[bytes, int, int]:
    with Image.open(path) as image:
        frame = image.convert("RGB")
        if frame.width > max_width:
            height = max(1, round(frame.height * max_width / frame.width))
            frame = frame.resize((max_width, height), Image.Resampling.BILINEAR)
        buffer = io.BytesIO()
        frame.save(buffer, format="JPEG", quality=82)
        return buffer.getvalue(), frame.width, frame.height


def _body_pose(samples: tuple[_GroundTruth, ...], t_ns: int) -> tuple[Pose, bool]:
    if not samples:
        return Pose(Vec3(0.0, 0.0, 0.0)), False
    times = [sample.t_ns for sample in samples]
    index = bisect.bisect_left(times, t_ns)
    if index >= len(samples):
        return samples[-1].pose, True
    if index == 0:
        return samples[0].pose, True
    earlier = samples[index - 1]
    later = samples[index]
    if abs(t_ns - earlier.t_ns) <= abs(later.t_ns - t_ns):
        return earlier.pose, True
    return later.pose, True


def _load_groundtruth(prepared: PreparedDataset) -> tuple[_GroundTruth, ...]:
    path = _ensure_groundtruth(prepared)
    if path is None:
        return ()
    samples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = [part.strip() for part in stripped.split(",")]
        if len(parts) < 8:
            continue
        qw, qx, qy, qz = (float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7]))
        samples.append(
            _GroundTruth(
                int(float(parts[0])),
                Pose(
                    Vec3(float(parts[1]), float(parts[2]), float(parts[3])),
                    (qx, qy, qz, qw),
                ),
            )
        )
    return tuple(samples)


def _ensure_groundtruth(prepared: PreparedDataset) -> Path | None:
    direct = prepared.root / "mav0" / "state_groundtruth_estimate0" / "data.csv"
    if direct.is_file():
        return direct
    archive_path = prepared.root.parent / "downloads" / f"{prepared.spec.dataset_id}.zip"
    if not archive_path.is_file():
        return None
    suffix = "mav0/state_groundtruth_estimate0/data.csv"
    with zipfile.ZipFile(archive_path) as archive:
        member = next(
            (name for name in archive.namelist() if name.endswith(suffix) and ".." not in name),
            None,
        )
        if member is None:
            return None
        direct.parent.mkdir(parents=True, exist_ok=True)
        direct.write_bytes(archive.read(member))
    return direct


def _t_bs(
    text: str,
) -> tuple[
    tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]],
    tuple[float, float, float],
]:
    match = re.search(r"data:\s*\[([^\]]+)\]", text)
    identity = (
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        (0.0, 0.0, 0.0),
    )
    if match is None:
        return identity
    numbers = [float(part) for part in match.group(1).split(",")]
    if len(numbers) < 16:
        return identity
    rotation = (
        (numbers[0], numbers[1], numbers[2]),
        (numbers[4], numbers[5], numbers[6]),
        (numbers[8], numbers[9], numbers[10]),
    )
    translation = (numbers[3], numbers[7], numbers[11])
    return rotation, translation
