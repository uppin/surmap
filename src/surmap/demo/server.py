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
import itertools
import json
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.datasets import (
    DatasetSpec,
    DemoCalibration,
    PreparedDataset,
    load_calibration,
    scaled_sensor_yaml,
)
from surmap.demo.page import PAGE
from surmap.detection.detector import CoralDetector, decode_rgb
from surmap.detection.profiles import DEFAULT_PROFILE, MODEL_PROFILES
from surmap.detection.source import CoralDetectionSource, DetectionSource
from surmap.detection.tracker import TrackedDetection
from surmap.slam.base import FrameResult
from surmap.slam.sidecar import SidecarRtabmapBackend
from surmap.slam.stream_protocol import Keypoint, MapUpdate, OdomUpdate, Rectification
from surmap.slam.streaming import MapCloud, StreamingRtabmapBackend
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
    def map_cloud(self) -> MapCloud: ...
    def frame_odometry(self, frame_id: int) -> OdomUpdate | None: ...
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
    @property
    def rectification(self) -> Rectification | None: ...


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


# Overlay ramp colours, near to far; each dataset sets the depths
# (`DatasetSpec.depth_stops_m`) and the page legend shows the same stops.
DEPTH_COLOURS: tuple[tuple[int, int, int], ...] = (
    (0xFF, 0x5A, 0x3C),  # near: red
    (0xFF, 0xB0, 0x3A),  # mid: orange
    (0x2F, 0xD4, 0xC4),  # far: teal
)
DepthStops = tuple[float, float, float]
INDOOR_STOPS: DepthStops = (1.0, 3.0, 6.0)

OverlayPoint = dict[str, float | str]


@dataclass(frozen=True)
class StreamBackendOptions:
    """How the live sidecar is configured for one prepared dataset."""

    cam0_yaml: str
    cam1_yaml: str
    width: int
    height: int
    max_depth_m: float


def stream_backend_options(prepared: PreparedDataset) -> StreamBackendOptions:
    """The live sidecar's configuration: display-size frames and calibration."""
    width, height = prepared.spec.display_size
    return StreamBackendOptions(
        cam0_yaml=scaled_sensor_yaml(prepared.sensor_yaml("cam0"), width, height),
        cam1_yaml=scaled_sensor_yaml(prepared.sensor_yaml("cam1"), width, height),
        width=width,
        height=height,
        max_depth_m=prepared.spec.max_map_depth_m,
    )


def depth_colour(depth_m: float, stops: DepthStops = INDOOR_STOPS) -> str:
    """Overlay colour for a depth: red near, orange mid, teal far."""
    ramp = list(zip(stops, DEPTH_COLOURS, strict=True))
    rgb = ramp[0][1] if depth_m <= ramp[0][0] else ramp[-1][1]
    for (low, low_rgb), (high, high_rgb) in itertools.pairwise(ramp):
        if low < depth_m <= high:
            rgb = _blend(low_rgb, high_rgb, (depth_m - low) / (high - low))
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def rectified_to_raw(
    pixels: NDArray[np.float64], rectification: Rectification
) -> NDArray[np.float64]:
    """Rectified left-camera pixels to raw (distorted) display pixels.

    Undoes the rectification rotation (raw ray = R1ᵀ · rectified ray), then
    applies the raw camera's radial-tangential distortion.
    """
    fx, fy, cx, cy = rectification.rectified
    rays = np.stack(
        [(pixels[:, 0] - cx) / fx, (pixels[:, 1] - cy) / fy, np.ones(len(pixels))], axis=1
    )
    # Row vectors: R1ᵀ · r is r @ R1.
    raw_rays = rays @ np.array(rectification.rotation, dtype=np.float64).reshape(3, 3)
    x = raw_rays[:, 0] / raw_rays[:, 2]
    y = raw_rays[:, 1] / raw_rays[:, 2]
    k1, k2, p1, p2 = rectification.distortion
    r2 = x * x + y * y
    radial = 1 + k1 * r2 + k2 * r2 * r2
    xd = x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
    yd = y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
    raw_fx, raw_fy, raw_cx, raw_cy = rectification.raw
    return np.stack([raw_fx * xd + raw_cx, raw_fy * yd + raw_cy], axis=1)


def _coloured(
    points: list[dict[str, float]], stops: DepthStops = INDOOR_STOPS
) -> list[OverlayPoint]:
    return [{**point, "c": depth_colour(point["d"], stops)} for point in points]


def keypoint_overlay(
    keypoints: tuple[Keypoint, ...],
    rectification: Rectification | None,
    calibration: DemoCalibration,
    stops: DepthStops = INDOOR_STOPS,
) -> list[OverlayPoint]:
    """A frame's tracked keypoints at their raw display pixels, coloured by depth."""
    if not keypoints:
        return []
    pixels = np.array([(k.u, k.v) for k in keypoints], dtype=np.float64)
    if rectification is not None:
        pixels = rectified_to_raw(pixels, rectification)
    points = [
        {"x": round(u, 1), "y": round(v, 1), "d": round(k.depth, 2)}
        for (u, v), k in zip(pixels.tolist(), keypoints, strict=True)
        if 0 <= u < calibration.width and 0 <= v < calibration.height
    ]
    return _coloured(points, stops)


def _floor_plane_cloud(cloud: MapCloud, max_points: int = MAX_MAP_POINTS) -> list[list[float]]:
    """Live map points on the floor plane as [x, z, r, g, b].

    The live map is in RTAB-Map's optical-world frame (x right, y down,
    z forward from the first camera pose), so the floor plane is x-z.
    """
    points, colors = cloud.points, cloud.colors
    if len(points) > max_points:
        pick = np.arange(max_points) * len(points) // max_points
        points, colors = points[pick], colors[pick]
    return [
        [round(x, 3), round(z, 3), r, g, b]
        for (x, _, z), (r, g, b) in zip(points.tolist(), colors.tolist(), strict=True)
    ]


def _floor_plane_trajectory(trajectory: list[Pose]) -> list[list[float]]:
    return [[round(pose.position.x, 3), round(pose.position.z, 3)] for pose in trajectory]


class _DetectionWorker:
    """Runs the detector off the frame loop, on the newest submitted frame.

    A frame submitted while another waits replaces it (latest-only), so a
    slow detector skips frames instead of stalling playback. Results come
    back in frame order.
    """

    def __init__(self, source: DetectionSource, size: tuple[int, int]) -> None:
        self._source = source
        self._size = size
        self._condition = threading.Condition()
        self._pending: tuple[int, int, bytes] | None = None
        self._busy = False
        self._closed = False
        self._results: list[DemoEvent] = []
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, frame_id: int, t_ns: int, jpeg: bytes) -> None:
        with self._condition:
            self._pending = (frame_id, t_ns, jpeg)
            self._condition.notify_all()

    def poll(self) -> list[DemoEvent]:
        with self._condition:
            if self._error is not None:
                raise self._error
            done, self._results = self._results, []
            return done

    def drain(self, timeout: float = 30.0) -> list[DemoEvent]:
        """Wait for the in-flight and pending frames, then return their results."""
        with self._condition:
            self._condition.wait_for(
                lambda: (self._pending is None and not self._busy) or self._error is not None,
                timeout=timeout,
            )
        return self.poll()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending is not None or self._closed)
                if self._closed:
                    return
                assert self._pending is not None
                frame_id, t_ns, jpeg = self._pending
                self._pending, self._busy = None, True
            try:
                rgb = decode_rgb(FrameImage(*self._size, "mjpeg", jpeg))
                event = _detections_event(
                    frame_id, t_ns, self._source.detect_tracked(frame_id, rgb)
                )
            except BaseException as exc:  # surfaced on the playback thread
                with self._condition:
                    self._error, self._busy = exc, False
                    self._condition.notify_all()
                return
            with self._condition:
                self._results.append(event)
                self._busy = False
                self._condition.notify_all()


def _detections_event(frame_id: int, t_ns: int, tracked: tuple[TrackedDetection, ...]) -> DemoEvent:
    # A separate event, keyed by frame_id — detections are not attached
    # to the frame event; the page joins them by frame_id like a wire
    # client would.
    return DemoEvent(
        "detections",
        {
            "frame_id": frame_id,
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


def _display_jpeg(prepared: PreparedDataset, channel: int, t_ns: int) -> bytes:
    """The half-res JPEG for one frame, generated once and cached."""
    width, height = prepared.spec.display_size
    target = prepared.root / f"display-{width}x{height}" / f"cam{channel}" / f"{t_ns}.jpg"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(prepared.frame_path(channel, t_ns)) as frame:
            frame.resize((width, height)).convert("L").save(target, format="JPEG", quality=85)
    return target.read_bytes()


# A live frame waits at most this long for its odometry before it is
# shown without keypoints (its pair may have been dropped).
HOLD_MAX_S = 2.0


@dataclass
class _HeldFrame:
    index: int
    frame_id: int
    t_ns: int
    jpeg: bytes
    held_at: float
    overlay: list[OverlayPoint] | None = None  # known up front without live SLAM


class _Display:
    """Shows frames in order, each once its overlay is known.

    With live SLAM a frame waits for its own odometry, so its keypoints
    are the ones RTAB-Map tracked on that very image; detections are
    released only once their frame has been shown, never ahead of it.
    """

    def __init__(
        self,
        total: int,
        backend: LiveSlamBackend | None,
        calibration: DemoCalibration,
        stops: DepthStops,
    ) -> None:
        self._total = total
        self._stops = stops
        self._backend = backend
        self._calibration = calibration
        self._frames: deque[_HeldFrame] = deque()
        self._detections: list[DemoEvent] = []
        self._shown = 0

    def add_frame(self, frame: _HeldFrame) -> None:
        self._frames.append(frame)

    def add_detections(self, events: list[DemoEvent]) -> None:
        self._detections.extend(events)

    def release(self, *, final: bool = False) -> Iterator[DemoEvent]:
        while self._frames:
            head = self._frames[0]
            overlay = self._overlay_for(head, final)
            if overlay is None:
                break
            self._frames.popleft()
            self._shown = head.frame_id
            yield DemoEvent(
                "frame",
                {
                    "index": head.index,
                    "total": self._total,
                    "frame_id": head.frame_id,
                    "t_ns": head.t_ns,
                    "detections": overlay,
                    "point_count": len(overlay),
                },
                jpeg=head.jpeg,
            )
        ready = [
            event
            for event in self._detections
            if final or int(str(event.data["frame_id"])) <= self._shown
        ]
        self._detections = [event for event in self._detections if event not in ready]
        yield from ready

    def _overlay_for(self, frame: _HeldFrame, final: bool) -> list[OverlayPoint] | None:
        if frame.overlay is not None:
            return frame.overlay
        backend = self._backend
        assert backend is not None
        odom = backend.frame_odometry(frame.frame_id)
        if odom is not None:
            return keypoint_overlay(
                odom.keypoints, backend.rectification, self._calibration, self._stops
            )
        given_up = (
            final
            or backend.last_odom_frame > frame.frame_id  # its pair was dropped
            or time.monotonic() - frame.held_at > HOLD_MAX_S
        )
        return [] if given_up else None


class DemoPlayer:
    """Plays one prepared dataset as demo events (see module docs)."""

    def __init__(
        self,
        prepared: PreparedDataset,
        *,
        fps: float | None = None,
        max_frames: int = 0,
        start_index: int = 0,
        with_rtabmap: bool = True,
        stereo: StereoReconstructor | None = None,
        detection_source: DetectionSource | None = None,
        rtabmap_mode: str = "live",
        backend_factory: Callable[[], SidecarRtabmapBackend | LiveSlamBackend] | None = None,
    ) -> None:
        fps = prepared.spec.fps if fps is None else fps
        if fps <= 0:
            raise ValueError("fps must be positive")
        self._prepared = prepared
        self._native = load_calibration(prepared)
        self._size = prepared.spec.display_size
        self._calibration = self._native.scaled(*self._size)
        self._fps = fps
        self._max_frames = max_frames
        self._start_index = start_index
        self._with_rtabmap = with_rtabmap
        self._stereo = stereo if stereo is not None else StereoReconstructor()
        self._detection_source = detection_source
        if rtabmap_mode not in ("live", "batch"):
            raise ValueError("rtabmap_mode must be 'live' or 'batch'")
        if with_rtabmap and rtabmap_mode == "batch" and not prepared.has_imu:
            raise ValueError(
                f"{prepared.spec.dataset_id} has no IMU; the batch sidecar needs one "
                "(use --rtabmap-mode live)"
            )
        self._rtabmap_mode = rtabmap_mode
        self._backend_factory = backend_factory

    def _map_event(self, backend: LiveSlamBackend, frame_id: int) -> DemoEvent:
        cloud = backend.map_cloud()
        trajectory = backend.trajectory()
        return DemoEvent(
            "map",
            {
                "frame_id": frame_id,
                "cloud_xy": _floor_plane_cloud(cloud),
                "cloud_points": len(cloud.points),
                "trajectory_xy": _floor_plane_trajectory(trajectory),
                "keyframes": backend.keyframe_count,
                "odom_state": backend.odom_state,
                "lag_frames": max(0, frame_id - backend.last_odom_frame),
                "dropped_frames": backend.dropped_frames,
            },
        )

    @property
    def fps(self) -> float:
        return self._fps

    def _backend(self) -> SidecarRtabmapBackend | LiveSlamBackend:
        if self._backend_factory is not None:
            return self._backend_factory()
        prepared = self._prepared
        options = stream_backend_options(prepared)
        if self._rtabmap_mode == "live":
            return StreamingRtabmapBackend(
                cam0_yaml=options.cam0_yaml,
                cam1_yaml=options.cam1_yaml,
                width=options.width,
                height=options.height,
                max_depth_m=options.max_depth_m,
            )
        return SidecarRtabmapBackend(
            cam0_yaml=options.cam0_yaml,
            cam1_yaml=options.cam1_yaml,
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
        worker = (
            _DetectionWorker(self._detection_source, self._size)
            if self._detection_source is not None
            else None
        )
        live = backend if isinstance(backend, LiveSlamBackend) else None
        display = _Display(len(timestamps), live, calibration, prepared.spec.depth_stops_m)
        last_map_emit = 0.0
        try:
            for index, t_ns in enumerate(timestamps):
                frame_started = time.monotonic()
                left_jpeg = _display_jpeg(prepared, 0, t_ns)
                right_jpeg = _display_jpeg(prepared, 1, t_ns)
                if worker is not None:
                    worker.submit(index + 1, t_ns, left_jpeg)
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
                held = _HeldFrame(index, index + 1, t_ns, left_jpeg, time.monotonic())
                if live is None:
                    points = self._stereo.reconstruct(
                        FrameImage(*self._size, "mjpeg", left_jpeg),
                        FrameImage(*self._size, "mjpeg", right_jpeg),
                        rig,
                    )
                    held.overlay = _coloured(
                        project_overlay(points, calibration), prepared.spec.depth_stops_m
                    )
                display.add_frame(held)
                if worker is not None:
                    display.add_detections(worker.poll())
                if isinstance(backend, LiveSlamBackend):
                    backend.poll_updates()
                yield from display.release()
                if isinstance(backend, LiveSlamBackend):
                    now = time.monotonic()
                    if now - last_map_emit >= 0.33:
                        last_map_emit = now
                        yield self._map_event(backend, index + 1)
                # Server-side pacing: one frame interval per frame,
                # however long processing took — never a catch-up burst.
                remaining = 1.0 / self._fps - (time.monotonic() - frame_started)
                if remaining > 0:
                    time.sleep(remaining)
            if worker is not None:
                display.add_detections(worker.drain())
            yield from display.release()
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
                yield from display.release(final=True)
                trajectory = backend.trajectory()
                cloud = results[-1].static_points if results else ()
                if isinstance(backend, LiveSlamBackend):
                    live_cloud = backend.map_cloud()
                    cloud_xy = _floor_plane_cloud(live_cloud)
                    trajectory_xy = _floor_plane_trajectory(trajectory)
                else:
                    # The batch sidecar's map is z-up (EuRoC base frame).
                    sample = cloud
                    if len(sample) > MAX_MAP_POINTS:
                        step = len(sample) / MAX_MAP_POINTS
                        sample = tuple(sample[int(i * step)] for i in range(MAX_MAP_POINTS))
                    cloud_xy = [[round(p.x, 3), round(p.y, 3)] for p in sample]
                    trajectory_xy = [
                        [round(pose.position.x, 3), round(pose.position.y, 3)]
                        for pose in trajectory
                    ]
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
                yield DemoEvent(
                    "final",
                    {
                        "poses": len(trajectory),
                        "travelled_m": round(travelled, 3),
                        "cloud_points": len(cloud),
                        "cloud_xy": cloud_xy,
                        "trajectory_xy": trajectory_xy,
                    },
                )
            yield from display.release(final=True)
        finally:
            if worker is not None:
                worker.close()
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


def _metres(value: float) -> str:
    return f"{value:g} m"


def _page_tuning(spec: DatasetSpec) -> dict[str, object]:
    """Per-dataset values the page template needs: view size, ramp, credit."""
    near, mid, far = spec.depth_stops_m
    width, height = spec.display_size
    return {
        "width": width,
        "height": height,
        "near": depth_colour(near, spec.depth_stops_m),
        "mid": depth_colour(mid, spec.depth_stops_m),
        "far": depth_colour(far, spec.depth_stops_m),
        "near_label": f"≤{_metres(near)}",
        "mid_label": _metres(mid),
        "far_label": f"≥{_metres(far)}",
        "near_m": near,
        "credit": html.escape(f"Data: {spec.credit}") if spec.credit else "",
    }


def make_demo_server(
    prepared: PreparedDataset,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    fps: float | None = None,
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
                **_page_tuning(self.server.prepared.spec),
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
