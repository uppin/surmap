"""Demo server: recorded stereo in, live video + detections out.

One browser page, two server-sent event types:

- `frame`: the current left frame (JPEG, base64) with the stereo
  reconstructor's scene points projected back onto it as overlay
  detections, paced server-side at the requested frame rate (the
  first frame is sent promptly; a slow frame never causes a burst).
- `final` (with RTAB-Map enabled): after the last frame, the real
  RTAB-Map sidecar — which staged every played pair — flushes, and
  its optimized trajectory + assembled cloud are sent for the map
  panel. The sidecar is closed whatever happens (completion, client
  disconnect, error), via the generator's `finally`.

Playback state is per connection and guarded: one viewer at a time.
"""

from __future__ import annotations

import base64
import html
import json
import math
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.datasets import (
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    DemoCalibration,
    PreparedDataset,
    load_calibration,
    scaled_sensor_yaml,
)
from surmap.demo.page import PAGE
from surmap.detection.detector import CoralDetector, decode_rgb
from surmap.detection.profiles import DEFAULT_PROFILE, MODEL_PROFILES
from surmap.detection.source import CoralDetectionSource, DetectionSource
from surmap.slam.base import FrameResult
from surmap.slam.sidecar import SidecarRtabmapBackend
from surmap.slam.stream_protocol import MapUpdate
from surmap.slam.streaming import StreamingRtabmapBackend
from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from surmap.types import Pose, StereoFramePair, Vec3

MAX_OVERLAY_POINTS = 600
MAX_MAP_POINTS = 4000


@runtime_checkable
class LiveSlamBackend(Protocol):
    """The streaming-backend surface the demo's live map uses."""

    def process_frame(self, frame: StereoFramePair) -> FrameResult: ...
    def poll_updates(self) -> list[MapUpdate]: ...
    def map_snapshot(self) -> tuple[Vec3, ...]: ...
    def trajectory(self) -> list[Pose]: ...
    def flush(self) -> list[FrameResult]: ...
    def close(self) -> None: ...

    @property
    def dropped_frames(self) -> int: ...
    @property
    def odom_state(self) -> str: ...
    @property
    def last_odom_frame(self) -> int: ...
    @property
    def keyframe_count(self) -> int: ...


@dataclass(frozen=True)
class DemoEvent:
    kind: str  # "frame" | "status" | "final" | "map" | "detections"
    data: dict[str, object]
    jpeg: bytes = b""


def project_overlay(
    points: tuple[Vec3, ...], calibration: DemoCalibration, max_points: int = MAX_OVERLAY_POINTS
) -> list[dict[str, float]]:
    """Camera-frame points projected to display pixels, evenly sampled."""
    visible = []
    for point in points:
        if point.z <= 0.05:
            continue
        u = calibration.fx * point.x / point.z + calibration.cx
        v = calibration.fy * point.y / point.z + calibration.cy
        if 0.0 <= u < calibration.width and 0.0 <= v < calibration.height:
            visible.append({"x": round(u, 1), "y": round(v, 1), "d": round(point.z, 2)})
    if len(visible) > max_points:
        step = len(visible) / max_points
        visible = [visible[int(index * step)] for index in range(max_points)]
    return visible


def project_map_overlay(
    points: NDArray[np.float32],
    camera_pose: Pose,
    calibration: DemoCalibration,
    max_points: int = MAX_OVERLAY_POINTS,
) -> list[dict[str, float]]:
    """Map-frame points seen from `camera_pose`, projected to display pixels."""
    raise NotImplementedError("TODO(live-map-display): project_map_overlay")


def _display_jpeg(prepared: PreparedDataset, channel: int, t_ns: int) -> bytes:
    """The half-res JPEG for one frame, generated once and cached."""
    target = prepared.root / "display" / f"cam{channel}" / f"{t_ns}.jpg"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(prepared.frame_path(channel, t_ns)) as frame:
            frame.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT)).convert("L").save(
                target, format="JPEG", quality=85
            )
    return target.read_bytes()


class DemoPlayer:
    """Plays one prepared dataset as demo events (see module docs)."""

    def __init__(
        self,
        prepared: PreparedDataset,
        *,
        fps: float = 20.0,
        max_frames: int = 0,
        start_index: int = 0,
        with_rtabmap: bool = True,
        stereo: StereoReconstructor | None = None,
        detection_source: DetectionSource | None = None,
        rtabmap_mode: str = "live",
        backend_factory: Callable[[], SidecarRtabmapBackend | LiveSlamBackend] | None = None,
    ) -> None:
        if fps <= 0:
            raise ValueError("fps must be positive")
        self._prepared = prepared
        self._native = load_calibration(prepared)
        self._calibration = self._native.scaled(DISPLAY_WIDTH, DISPLAY_HEIGHT)
        self._fps = fps
        self._max_frames = max_frames
        self._start_index = start_index
        self._with_rtabmap = with_rtabmap
        self._stereo = stereo if stereo is not None else StereoReconstructor()
        self._detection_source = detection_source
        if rtabmap_mode not in ("live", "batch"):
            raise ValueError("rtabmap_mode must be 'live' or 'batch'")
        self._rtabmap_mode = rtabmap_mode
        self._backend_factory = backend_factory

    def _map_event(self, backend: LiveSlamBackend, frame_id: int) -> DemoEvent:
        cloud = backend.map_snapshot()
        sample = cloud
        if len(sample) > MAX_MAP_POINTS:
            step = len(sample) / MAX_MAP_POINTS
            sample = tuple(sample[int(i * step)] for i in range(MAX_MAP_POINTS))
        trajectory = backend.trajectory()
        return DemoEvent(
            "map",
            {
                "frame_id": frame_id,
                "cloud_xy": [[round(p.x, 3), round(p.y, 3)] for p in sample],
                "cloud_points": len(cloud),
                "trajectory_xy": [
                    [round(p.position.x, 3), round(p.position.y, 3)] for p in trajectory
                ],
                "keyframes": backend.keyframe_count,
                "odom_state": backend.odom_state,
                "lag_frames": max(0, frame_id - backend.last_odom_frame),
                "dropped_frames": backend.dropped_frames,
            },
        )

    def _backend(self) -> SidecarRtabmapBackend | LiveSlamBackend:
        if self._backend_factory is not None:
            return self._backend_factory()
        prepared = self._prepared
        if self._rtabmap_mode == "live":
            return StreamingRtabmapBackend(
                cam0_yaml=scaled_sensor_yaml(
                    prepared.sensor_yaml("cam0"), DISPLAY_WIDTH, DISPLAY_HEIGHT
                ),
                cam1_yaml=scaled_sensor_yaml(
                    prepared.sensor_yaml("cam1"), DISPLAY_WIDTH, DISPLAY_HEIGHT
                ),
            )
        return SidecarRtabmapBackend(
            cam0_yaml=scaled_sensor_yaml(
                prepared.sensor_yaml("cam0"), DISPLAY_WIDTH, DISPLAY_HEIGHT
            ),
            cam1_yaml=scaled_sensor_yaml(
                prepared.sensor_yaml("cam1"), DISPLAY_WIDTH, DISPLAY_HEIGHT
            ),
            imu_yaml=prepared.sensor_yaml("imu0"),
            imu_csv=prepared.imu_csv(),
        )

    def events(self) -> Iterator[DemoEvent]:
        prepared = self._prepared
        calibration = self._calibration
        rig = StereoRig(
            fx=calibration.fx,
            fy=calibration.fy,
            cx=calibration.cx,
            cy=calibration.cy,
            baseline_m=calibration.baseline_m,
        )
        timestamps = prepared.timestamps_ns[self._start_index :]
        if self._max_frames > 0:
            timestamps = timestamps[: self._max_frames]
        backend = self._backend() if self._with_rtabmap else None
        last_map_emit = 0.0
        try:
            for index, t_ns in enumerate(timestamps):
                frame_started = time.monotonic()
                left_jpeg = _display_jpeg(prepared, 0, t_ns)
                right_jpeg = _display_jpeg(prepared, 1, t_ns)
                points = self._stereo.reconstruct(
                    FrameImage(DISPLAY_WIDTH, DISPLAY_HEIGHT, "mjpeg", left_jpeg),
                    FrameImage(DISPLAY_WIDTH, DISPLAY_HEIGHT, "mjpeg", right_jpeg),
                    rig,
                )
                if backend is not None:
                    backend.process_frame(
                        StereoFramePair(
                            frame_id=index + 1,
                            t_ns=t_ns,
                            left_ref="demo-left",
                            right_ref="demo-right",
                            calibration_id=prepared.spec.dataset_id,
                            left_data=left_jpeg,
                            right_data=right_jpeg,
                        )
                    )
                yield DemoEvent(
                    "frame",
                    {
                        "index": index,
                        "total": len(timestamps),
                        "frame_id": index + 1,
                        "t_ns": t_ns,
                        "detections": project_overlay(points, calibration),
                        "point_count": len(points),
                    },
                    jpeg=left_jpeg,
                )
                if self._detection_source is not None:
                    # A separate event, keyed by frame_id — detections
                    # are not attached to the frame event; the page
                    # joins them by frame_id like a wire client would.
                    rgb = decode_rgb(FrameImage(DISPLAY_WIDTH, DISPLAY_HEIGHT, "mjpeg", left_jpeg))
                    tracked = self._detection_source.detect_tracked(index + 1, rgb)
                    yield DemoEvent(
                        "detections",
                        {
                            "frame_id": index + 1,
                            "t_ns": t_ns,
                            "objects": [
                                {
                                    "label": detection.label,
                                    "score": round(detection.score, 2),
                                    "track_id": detection.track_id,
                                    "box": [round(value, 1) for value in detection.box_xyxy],
                                }
                                for detection in tracked
                            ],
                        },
                    )
                if isinstance(backend, LiveSlamBackend):
                    backend.poll_updates()
                    now = time.monotonic()
                    if now - last_map_emit >= 0.33:
                        last_map_emit = now
                        yield self._map_event(backend, index + 1)
                # Server-side pacing: one frame interval per frame,
                # however long processing took — never a catch-up burst.
                remaining = 1.0 / self._fps - (time.monotonic() - frame_started)
                if remaining > 0:
                    time.sleep(remaining)
            if backend is not None:
                yield DemoEvent(
                    "status",
                    {
                        "message": (
                            "Finalizing RTAB-Map graph…"
                            if isinstance(backend, LiveSlamBackend)
                            else "Building the RTAB-Map map from all played frames…"
                        )
                    },
                )
                results = backend.flush()
                trajectory = backend.trajectory()
                cloud = results[-1].static_points if results else ()
                travelled = 0.0
                if trajectory:
                    origin = trajectory[0].position
                    travelled = max(
                        math.dist(
                            (pose.position.x, pose.position.y, pose.position.z),
                            (origin.x, origin.y, origin.z),
                        )
                        for pose in trajectory
                    )
                sample = cloud
                if len(sample) > MAX_MAP_POINTS:
                    step = len(sample) / MAX_MAP_POINTS
                    sample = tuple(sample[int(i * step)] for i in range(MAX_MAP_POINTS))
                yield DemoEvent(
                    "final",
                    {
                        "poses": len(trajectory),
                        "travelled_m": round(travelled, 3),
                        "cloud_points": len(cloud),
                        "cloud_xy": [[round(p.x, 3), round(p.y, 3)] for p in sample],
                        "trajectory_xy": [
                            [round(pose.position.x, 3), round(pose.position.y, 3)]
                            for pose in trajectory
                        ],
                    },
                )
        finally:
            if backend is not None:
                backend.close()


class _DemoHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    prepared: PreparedDataset
    player_options: dict[str, object]
    stream_lock: threading.Lock


def coral_detection_source(model_dir: Path, model: str = DEFAULT_PROFILE) -> CoralDetectionSource:
    """The real Coral detector+tracker (CPU twin) for the demo."""
    profile = MODEL_PROFILES[model]
    detector = CoralDetector(
        model_dir / profile.file_for(use_edgetpu=False), model_dir / "coco_labels.txt"
    )
    return CoralDetectionSource(detector)


def make_demo_server(
    prepared: PreparedDataset,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    fps: float = 20.0,
    max_frames: int = 0,
    start_index: int = 0,
    with_rtabmap: bool = True,
    coral_model_dir: Path | None = None,
    coral_model: str = DEFAULT_PROFILE,
    rtabmap_mode: str = "live",
) -> ThreadingHTTPServer:
    """The demo HTTP server (not yet serving); caller serves/closes it."""
    options: dict[str, object] = {
        "fps": fps,
        "max_frames": max_frames,
        "start_index": start_index,
        "with_rtabmap": with_rtabmap,
        "rtabmap_mode": rtabmap_mode,
        "detection_source": (
            coral_detection_source(coral_model_dir, coral_model) if coral_model_dir else None
        ),
    }
    server = _DemoHttpServer((host, port), _DemoHandler)
    server.prepared = prepared
    server.player_options = options
    server.stream_lock = threading.Lock()
    return server


class _DemoHandler(BaseHTTPRequestHandler):
    server: _DemoHttpServer

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, "application/json", b'{"status": "ok"}')
            return
        if self.path == "/":
            page = PAGE.format(
                title=html.escape(self.server.prepared.spec.title),
                description=html.escape(self.server.prepared.spec.description),
            )
            self._send(200, "text/html; charset=utf-8", page.encode())
            return
        if self.path == "/stream":
            self._stream()
            return
        self._send(404, "text/plain", b"not found")

    def _stream(self) -> None:
        if not self.server.stream_lock.acquire(blocking=False):
            self._send(409, "text/plain", b"a demo stream is already running")
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            player = DemoPlayer(self.server.prepared, **self.server.player_options)  # type: ignore[arg-type]
            for event in player.events():
                payload = dict(event.data)
                if event.kind == "frame":
                    payload["image_b64"] = base64.b64encode(event.jpeg).decode()
                chunk = f"event: {event.kind}\ndata: {json.dumps(payload)}\n\n".encode()
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # viewer went away; the player's finally tears down
        finally:
            self.server.stream_lock.release()


def page_title(prepared: PreparedDataset) -> str:
    """The demo page's heading for `prepared` (used by the launcher log)."""
    return f"SurMap demo — {prepared.spec.title}"
