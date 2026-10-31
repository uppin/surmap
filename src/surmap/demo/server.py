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
import io
import itertools
import json
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import parse_qs, urlsplit

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.datasets import (
    DATASETS,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    DatasetSpec,
    DemoCalibration,
    PreparedDataset,
    PrepareProgress,
    cached_dataset,
    default_cache_dir,
    ensure_dataset,
    load_calibration,
    scaled_sensor_yaml,
)
from surmap.demo.events import DemoEvent as DemoEvent
from surmap.demo.events import RegionPlacer, sam_event
from surmap.demo.history import RunHistoryStore
from surmap.demo.page import PAGE
from surmap.detection.detector import CoralDetector, decode_rgb
from surmap.detection.profiles import DEFAULT_PROFILE, MODEL_PROFILES
from surmap.detection.source import CoralDetectionSource, DetectionSource
from surmap.detection.tracker import TrackedDetection
from surmap.slam.base import FrameResult
from surmap.slam.regions import RegionPointSource
from surmap.slam.sidecar import SidecarRtabmapBackend
from surmap.slam.stream_protocol import Keypoint, MapUpdate, OdomUpdate, Rectification
from surmap.slam.streaming import MapCloud, StreamingRtabmapBackend, pose_rotation
from surmap.survey.sam import (
    CentredBoxVideoSamDetector,
    RawFrame,
    VideoSamDetector,
    VideoSamStreamer,
)
from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from surmap.types import Pose, StereoFramePair, Vec3

MAX_OVERLAY_POINTS = 600

# Cap on raw cloud points sent to the browser 3D view (and persisted per
# map snapshot): the full count still travels as `cloud_points`.
MAX_CLOUD_POINTS = 12000


def cloud_points(
    cloud: MapCloud, max_points: int = MAX_CLOUD_POINTS
) -> tuple[list[list[float]], list[list[int]]]:
    """A cloud as JSON-ready (points, colours), stably sampled to the cap.

    The sample must be *dense* (the cap fully used) and *stable* as
    the cloud grows. Two earlier samplers failed one each: a
    stride-over-the-list resampled wholesale per update (10–25 %
    of drawn points survived — flicker), and first-point-per-voxel
    starved surface clouds (far fewer voxels than the cap — sparse).

    Each point instead gets a rank that depends only on itself:
    a hash of its centimetre-quantised coordinates. The cap's
    lowest ranks are drawn. A point's rank never changes as the
    cloud grows, so growth only displaces the few drawn points a
    newcomer out-ranks (a few percent per update), while the cap
    always stays exactly filled.
    """
    points, colors = cloud.points, cloud.colors
    if len(points) > max_points:
        pick = _stable_pick(points, max_points)
        points, colors = points[pick], colors[pick]
    return (
        [[round(float(v), 3) for v in row] for row in points.tolist()],
        [[int(v) for v in row] for row in colors.tolist()],
    )


def _stable_pick(points: NDArray[np.float32], max_points: int) -> NDArray[np.int64]:
    """Indices of the `max_points` lowest coordinate-hash ranks."""
    quantized = np.rint(points * 100.0).astype(np.int64).view(np.uint64)
    rank = quantized[:, 0] * np.uint64(0x9E3779B97F4A7C15)
    rank ^= quantized[:, 1] * np.uint64(0xC2B2AE3D27D4EB4F)
    rank ^= quantized[:, 2] * np.uint64(0x165667B19E3779F9)
    rank ^= rank >> np.uint64(29)
    rank *= np.uint64(0xBF58476D1CE4E5B9)
    rank ^= rank >> np.uint64(32)
    lowest = np.argpartition(rank, max_points)[:max_points]
    return np.sort(lowest.astype(np.int64))


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


# Floor plan canvas (square, px), its padding, and how many points make a
# pixel fully opaque.
FLOOR_CANVAS_PX = 340
FLOOR_PADDING_PX = 10
FLOOR_SOLID_POINTS = 16

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


@dataclass(frozen=True)
class FloorExtent:
    """The floor-plan area shown, in map metres, and its canvas mapping."""

    min_x: float
    max_x: float
    min_z: float
    max_z: float

    @property
    def scale(self) -> float:
        """Canvas pixels per metre (uniform, so the plan is never squashed)."""
        span = max(self.max_x - self.min_x, self.max_z - self.min_z, 0.01)
        return (FLOOR_CANVAS_PX - 2 * FLOOR_PADDING_PX) / span

    def to_pixels(self, x: float, z: float) -> tuple[float, float]:
        return (
            FLOOR_PADDING_PX + (x - self.min_x) * self.scale,
            FLOOR_CANVAS_PX - FLOOR_PADDING_PX - (z - self.min_z) * self.scale,
        )

    def grown(self, xs: NDArray[np.float32], zs: NDArray[np.float32]) -> FloorExtent:
        """This extent widened to cover the given points (never shrinks)."""
        if not len(xs):
            return self
        return FloorExtent(
            min(self.min_x, float(np.min(xs))),
            max(self.max_x, float(np.max(xs))),
            min(self.min_z, float(np.min(zs))),
            max(self.max_z, float(np.max(zs))),
        )

    def as_list(self) -> list[float]:
        return [round(v, 3) for v in (self.min_x, self.max_x, self.min_z, self.max_z)]


def _first_extent(xs: NDArray[np.float32], zs: NDArray[np.float32]) -> FloorExtent:
    return FloorExtent(float(np.min(xs)), float(np.max(xs)), float(np.min(zs)), float(np.max(zs)))


def render_floor_plan(xz: NDArray[np.float32], grey: NDArray[np.uint8], extent: FloorExtent) -> str:
    """Every map point on the floor plan as one base64 RGBA PNG.

    Each pixel is the mean grey of the points falling in it; its opacity
    rises with how many do (log scale), so walls and edges — where points
    pile up — read as solid lines. Deterministic: no sampling.
    """
    size = FLOOR_CANVAS_PX
    scale = extent.scale
    u = np.floor(FLOOR_PADDING_PX + (xz[:, 0] - extent.min_x) * scale).astype(np.int64)
    v = np.floor(size - FLOOR_PADDING_PX - (xz[:, 1] - extent.min_z) * scale).astype(np.int64)
    inside = (u >= 0) & (u < size) & (v >= 0) & (v < size)
    index = v[inside] * size + u[inside]
    count = np.bincount(index, minlength=size * size)
    total = np.bincount(index, weights=grey[inside].astype(np.float64), minlength=size * size)
    seen = count > 0
    mean = np.zeros(size * size)
    mean[seen] = total[seen] / count[seen]
    alpha = np.zeros(size * size)
    alpha[seen] = np.clip(255 * np.log1p(count[seen]) / np.log1p(FLOOR_SOLID_POINTS), 0, 255)
    rgba = np.zeros((size * size, 4), np.uint8)
    rgba[:, 0] = rgba[:, 1] = rgba[:, 2] = np.round(mean).astype(np.uint8)
    rgba[:, 3] = np.round(alpha).astype(np.uint8)
    out = io.BytesIO()
    Image.fromarray(rgba.reshape(size, size, 4), "RGBA").save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode()


FloorCamera = dict[str, float]


def floor_camera(pose: Pose, calibration: DemoCalibration) -> FloorCamera:
    """The camera on the floor plan: position (x, z), unit heading and
    horizontal field of view.

    The heading is the optical axis (rotation's third column) projected
    onto the x-z floor plane; a camera looking straight down keeps +z.
    """
    rotation = pose_rotation(pose)
    dx, dz = float(rotation[0, 2]), float(rotation[2, 2])
    length = math.hypot(dx, dz)
    if length < 1e-6:
        dx, dz, length = 0.0, 1.0, 1.0
    fov = 2 * math.degrees(math.atan(calibration.width / 2 / calibration.fx))
    return {
        "x": round(pose.position.x, 3),
        "z": round(pose.position.z, 3),
        "dx": round(dx / length, 3),
        "dz": round(dz / length, 3),
        "fov_deg": round(fov, 1),
    }


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


class _SamWorker:
    """Runs the SAM video session off the frame loop, in frame order.

    Continuous (video) mode is stateful, so unlike the Coral worker
    this one never drops or reorders: every submitted frame is queued
    FIFO and tracked sequentially, however far behind playback it
    falls. Results come back in frame order.
    """

    def __init__(self, source: VideoSamDetector, size: tuple[int, int]) -> None:
        self._source = source
        self._size = size
        self._condition = threading.Condition()
        self._pending: deque[tuple[int, int, bytes]] = deque()
        self._busy = False
        self._closed = False
        self._results: list[DemoEvent] = []
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, frame_id: int, t_ns: int, jpeg: bytes) -> None:
        with self._condition:
            self._pending.append((frame_id, t_ns, jpeg))
            self._condition.notify_all()

    def poll(self) -> list[DemoEvent]:
        with self._condition:
            if self._error is not None:
                raise self._error
            done, self._results = self._results, []
            return done

    def drain(self, timeout: float = 120.0) -> list[DemoEvent]:
        """Wait for every queued frame to be tracked, then return results."""
        with self._condition:
            self._condition.wait_for(
                lambda: (not self._pending and not self._busy) or self._error is not None,
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
                self._condition.wait_for(lambda: bool(self._pending) or self._closed)
                if self._closed:
                    return
                frame_id, t_ns, jpeg = self._pending.popleft()
                self._busy = True
            try:
                width, height = self._size
                event = sam_event(
                    frame_id,
                    t_ns,
                    self._source.track(RawFrame(frame_id, t_ns, 0, width, height, "mjpeg", jpeg)),
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


class _SamStreamWorker:
    """Runs a whole-video SAM streamer off the frame loop.

    SAM 3.1's session propagates over the whole video at its own
    pace; results are queued in frame order and released by the
    display once their frame has been shown, exactly like the
    per-frame SAM worker's.
    """

    def __init__(
        self,
        streamer: VideoSamStreamer,
        frame_paths: list[Path],
        frame_keys: list[tuple[int, int]],
    ) -> None:
        self._streamer = streamer
        self._frame_paths = frame_paths
        self._frame_keys = frame_keys
        self._condition = threading.Condition()
        self._results: list[DemoEvent] = []
        self._done = False
        self._closed = False
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def poll(self) -> list[DemoEvent]:
        with self._condition:
            if self._error is not None:
                raise self._error
            done, self._results = self._results, []
            return done

    def drain(self, timeout: float = 1800.0) -> list[DemoEvent]:
        """Wait for propagation to finish, then return remaining results."""
        with self._condition:
            self._condition.wait_for(lambda: self._done or self._error is not None, timeout)
        return self.poll()

    def close(self) -> None:
        # Cooperative cancellation, checked per yielded frame: a
        # closed worker stops at the next frame instead of running
        # its whole video on the GPU behind the next viewer's worker
        # (stacked sessions OOM'd the card and starved the live one).
        self._closed = True
        self._thread.join(timeout=5)

    def _run(self) -> None:
        try:
            for index, detections in self._streamer.stream(self._frame_paths):
                if self._closed:
                    break
                frame_id, t_ns = self._frame_keys[index]
                with self._condition:
                    self._results.append(sam_event(frame_id, t_ns, detections))
                    self._condition.notify_all()
        except BaseException as exc:  # surfaced on the playback thread
            with self._condition:
                self._error = exc
                self._condition.notify_all()
        finally:
            with self._condition:
                self._done = True
                self._condition.notify_all()


def _display_jpeg(prepared: PreparedDataset, channel: int, t_ns: int) -> bytes:
    """The half-res JPEG for one frame, generated once and cached."""
    width, height = prepared.spec.display_size
    target = prepared.root / f"display-{width}x{height}" / f"cam{channel}" / f"{t_ns}.jpg"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(prepared.frame_path(channel, t_ns)) as frame:
            frame.resize((width, height)).convert("L").save(target, format="JPEG", quality=85)
    return target.read_bytes()


def _display_jpeg_path(prepared: PreparedDataset, channel: int, t_ns: int) -> Path:
    """The cached display-JPEG file for one frame (generated if needed)."""
    _display_jpeg(prepared, channel, t_ns)
    width, height = prepared.spec.display_size
    return prepared.root / f"display-{width}x{height}" / f"cam{channel}" / f"{t_ns}.jpg"


# A live frame waits at most this long for its odometry before it is
# shown without keypoints (its pair may have been dropped).
HOLD_MAX_S = 2.0

# Recent frame JPEGs kept so a SAM result can carry its own frame's
# image to the separate SAM pane, whenever it lands.
SAM_FRAME_CACHE = 256


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
    SAM results are on their own cadence (a separate pane): they are
    released as soon as they arrive, each with its frame's JPEG.
    """

    def __init__(
        self,
        total: int,
        backend: LiveSlamBackend | None,
        calibration: DemoCalibration,
        stops: DepthStops,
        size: tuple[int, int] = (DISPLAY_WIDTH, DISPLAY_HEIGHT),
    ) -> None:
        self._total = total
        # Regions are placed only by a backend that can answer them.
        self._regions: RegionPlacer | None = (
            RegionPlacer(backend, size) if isinstance(backend, RegionPointSource) else None
        )
        self._stops = stops
        self._backend = backend
        self._calibration = calibration
        self._frames: deque[_HeldFrame] = deque()
        self._detections: list[DemoEvent] = []
        self._sam: list[DemoEvent] = []
        self._jpegs: dict[int, bytes] = {}
        self._shown = 0

    def add_frame(self, frame: _HeldFrame) -> None:
        self._frames.append(frame)

    def add_detections(self, events: list[DemoEvent]) -> None:
        self._detections.extend(events)

    def add_sam(self, events: list[DemoEvent]) -> None:
        self._sam.extend(events)

    def release(self, *, final: bool = False) -> Iterator[DemoEvent]:
        while self._frames:
            head = self._frames[0]
            shown = self._overlay_for(head, final)
            if shown is None:
                break
            overlay, camera = shown
            self._frames.popleft()
            self._shown = head.frame_id
            self._jpegs[head.frame_id] = head.jpeg
            while len(self._jpegs) > SAM_FRAME_CACHE:
                self._jpegs.pop(next(iter(self._jpegs)))
            yield DemoEvent(
                "frame",
                {
                    "index": head.index,
                    "total": self._total,
                    "frame_id": head.frame_id,
                    "t_ns": head.t_ns,
                    "detections": overlay,
                    "point_count": len(overlay),
                    "camera": camera,
                },
                jpeg=head.jpeg,
            )
            yield from self._ready(final=False)
            if not final:
                # One frame per release: a backlog that built up while
                # SAM (or odometry) was slow drains at the caller's
                # playback pace instead of flashing past in a burst.
                break
        yield from self._ready(final=final)

    def _ready(self, *, final: bool) -> Iterator[DemoEvent]:
        """Detections for shown frames; SAM results as they arrive."""
        ready = [
            event
            for event in self._detections
            if final or int(str(event.data["frame_id"])) <= self._shown
        ]
        self._detections = [event for event in self._detections if event not in ready]
        yield from ready
        sam_ready = [
            event for event in self._sam if final or int(str(event.data["frame_id"])) in self._jpegs
        ]
        self._sam = [event for event in self._sam if event not in sam_ready]
        for event in sam_ready:
            frame_id = int(str(event.data["frame_id"]))
            yield DemoEvent("sam", event.data, jpeg=self._jpegs.get(frame_id, b""))
            if self._regions is not None:
                yield self._regions.region_event(event)

    def _overlay_for(
        self, frame: _HeldFrame, final: bool
    ) -> tuple[list[OverlayPoint], FloorCamera | None] | None:
        """(overlay, camera) once the frame can be shown, else None."""
        if frame.overlay is not None:
            return frame.overlay, None
        backend = self._backend
        assert backend is not None
        odom = backend.frame_odometry(frame.frame_id)
        if odom is not None:
            overlay = keypoint_overlay(
                odom.keypoints, backend.rectification, self._calibration, self._stops
            )
            # The map-corrected pose keeps the camera on its (optimised)
            # trajectory after loop closures; raw odometry drifts off it.
            pose = odom.map_pose or odom.pose
            camera = floor_camera(pose, self._calibration) if pose else None
            return overlay, camera
        given_up = (
            final
            or backend.last_odom_frame > frame.frame_id  # its pair was dropped
            or time.monotonic() - frame.held_at > HOLD_MAX_S
        )
        return ([], None) if given_up else None


class PlaybackControls:
    """Pause, resume or cancel one player from another thread."""

    def __init__(self) -> None:
        self._playing = threading.Event()
        self._playing.set()
        self._cancelled = threading.Event()

    @property
    def paused(self) -> bool:
        return not self._playing.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def pause(self) -> None:
        self._playing.clear()

    def resume(self) -> None:
        self._playing.set()

    def cancel(self) -> None:
        self._cancelled.set()
        self._playing.set()  # a paused player wakes up to stop

    def wait_while_paused(self, timeout: float) -> None:
        self._playing.wait(timeout)


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
        sam_source: VideoSamDetector | None = None,
        sam_detector: VideoSamDetector | None = None,
        sam_streamer: VideoSamStreamer | None = None,
        rtabmap_mode: str = "live",
        backend_factory: Callable[[], SidecarRtabmapBackend | LiveSlamBackend] | None = None,
        controls: PlaybackControls | None = None,
    ) -> None:
        self._controls = controls if controls is not None else PlaybackControls()
        self._extent: FloorExtent | None = None
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
        if sam_source is not None and sam_detector is not None:
            raise ValueError("pass only one of sam_source and sam_detector")
        self._sam_source = sam_source if sam_source is not None else sam_detector
        if self._sam_source is not None and sam_streamer is not None:
            raise ValueError("pass only one of sam_source and sam_streamer")
        self._sam_streamer = sam_streamer
        if rtabmap_mode not in ("live", "batch"):
            raise ValueError("rtabmap_mode must be 'live' or 'batch'")
        if with_rtabmap and rtabmap_mode == "batch" and not prepared.has_imu:
            raise ValueError(
                f"{prepared.spec.dataset_id} has no IMU; the batch sidecar needs one "
                "(use --rtabmap-mode live)"
            )
        self._rtabmap_mode = rtabmap_mode
        self._backend_factory = backend_factory

    def _floor_plan(
        self, xz: NDArray[np.float32], grey: NDArray[np.uint8], trajectory_xz: list[list[float]]
    ) -> dict[str, object]:
        """Map image + its (grow-only) extent + trajectory, for map/final events."""
        path = np.array(trajectory_xz, np.float32).reshape(-1, 2)
        everything = np.concatenate([xz.astype(np.float32), path])
        if len(everything):
            xs, zs = everything[:, 0], everything[:, 1]
            self._extent = (self._extent or _first_extent(xs, zs)).grown(xs, zs)
        extent = self._extent or FloorExtent(-1.0, 1.0, -1.0, 1.0)
        return {
            "floor_png": render_floor_plan(xz, grey, extent),
            "extent": extent.as_list(),
            "trajectory_xy": trajectory_xz,
        }

    def _map_event(self, backend: LiveSlamBackend, frame_id: int) -> DemoEvent:
        cloud = backend.map_cloud()
        points, colors = cloud_points(cloud)
        trajectory = backend.trajectory()
        return DemoEvent(
            "map",
            {
                "frame_id": frame_id,
                "points": points,
                "point_colors": colors,
                **self._floor_plan(
                    cloud.points[:, [0, 2]], cloud.colors[:, 0], _floor_plane_trajectory(trajectory)
                ),
                "cloud_points": len(cloud.points),
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
        sam_worker = _SamWorker(self._sam_source, self._size) if self._sam_source else None
        if self._sam_source is not None:
            self._sam_source.reset()  # a new playback is a new video
        stream_worker = (
            _SamStreamWorker(
                self._sam_streamer,
                [_display_jpeg_path(prepared, 0, t_ns) for t_ns in timestamps],
                [(index + 1, t_ns) for index, t_ns in enumerate(timestamps)],
            )
            if self._sam_streamer is not None
            else None
        )
        live = backend if isinstance(backend, LiveSlamBackend) else None
        display = _Display(
            len(timestamps), live, calibration, prepared.spec.depth_stops_m, self._size
        )
        last_map_emit = 0.0
        try:
            for index, t_ns in enumerate(timestamps):
                # Paused: no pairs reach SLAM and no new frames are shown,
                # but held frames keep resolving as their odometry lands.
                while self._controls.paused and not self._controls.cancelled:
                    if isinstance(backend, LiveSlamBackend):
                        backend.poll_updates()
                    yield from display.release()
                    self._controls.wait_while_paused(0.05)
                if self._controls.cancelled:
                    return
                frame_started = time.monotonic()
                left_jpeg = _display_jpeg(prepared, 0, t_ns)
                right_jpeg = _display_jpeg(prepared, 1, t_ns)
                if worker is not None:
                    worker.submit(index + 1, t_ns, left_jpeg)
                if sam_worker is not None:
                    sam_worker.submit(index + 1, t_ns, left_jpeg)
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
                if sam_worker is not None:
                    display.add_sam(sam_worker.poll())
                if stream_worker is not None:
                    display.add_sam(stream_worker.poll())
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
            if sam_worker is not None:
                display.add_sam(sam_worker.drain())
            if stream_worker is not None:
                display.add_sam(stream_worker.drain())
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
                if isinstance(backend, LiveSlamBackend):
                    live_cloud = backend.map_cloud()
                    final_points, final_colors = cloud_points(live_cloud)
                    final_count = len(live_cloud.points)
                    plan = self._floor_plan(
                        live_cloud.points[:, [0, 2]],
                        live_cloud.colors[:, 0],
                        _floor_plane_trajectory(trajectory),
                    )
                else:
                    # The batch sidecar's map is z-up (EuRoC base frame).
                    xy = np.array([(p.x, p.y) for p in cloud], np.float32).reshape(-1, 2)
                    final_points = [[round(p.x, 3), round(p.y, 3), round(p.z, 3)] for p in cloud]
                    if len(final_points) > MAX_CLOUD_POINTS:
                        step = len(final_points) / MAX_CLOUD_POINTS
                        final_points = [
                            final_points[int(i * step)] for i in range(MAX_CLOUD_POINTS)
                        ]
                    final_colors = [[160, 160, 160]] * len(final_points)
                    final_count = len(cloud)
                    plan = self._floor_plan(
                        xy,
                        np.full(len(xy), 160, np.uint8),
                        [[round(t.position.x, 3), round(t.position.y, 3)] for t in trajectory],
                    )
                yield DemoEvent(
                    "final",
                    {
                        "poses": len(trajectory),
                        "travelled_m": round(travelled, 3),
                        "cloud_points": final_count,
                        "points": final_points,
                        "point_colors": final_colors,
                        **plan,
                    },
                )
            yield from display.release(final=True)
        finally:
            if worker is not None:
                worker.close()
            if sam_worker is not None:
                sam_worker.close()
            if stream_worker is not None:
                stream_worker.close()
            # The streamer itself outlives one playback (its owner is
            # the server); only this playback's worker thread stops.
            if self._sam_source is not None:
                self._sam_source.close()
            if backend is not None:
                backend.close()


@dataclass
class _Preparation:
    """One scene's background download + extraction into the cache."""

    state: str = "preparing"  # preparing | ready | error
    progress: PrepareProgress | None = None
    error: str = ""


# A new viewer waits at most this long for the running stream to stop.
TAKEOVER_TIMEOUT_S = 10.0


class _DemoHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    catalog: dict[str, DatasetSpec]
    default_dataset: str
    cache_dir: Path
    fetch: Callable[[str, Path], None] | None
    player_options: dict[str, object]
    sam_enabled: bool
    sam_label: str
    stream_lock: threading.Lock
    state_lock: threading.Lock
    prepared: dict[str, PreparedDataset]
    preparations: dict[str, _Preparation]
    current: PlaybackControls | None
    history_store: RunHistoryStore

    def prepared_scene(self, dataset_id: str) -> PreparedDataset | None:
        with self.state_lock:
            found = self.prepared.get(dataset_id)
        if found is None:
            found = cached_dataset(self.catalog[dataset_id], self.cache_dir)
            if found is not None:
                with self.state_lock:
                    self.prepared[dataset_id] = found
        return found

    def scene_listing(self) -> dict[str, object]:
        scenes = []
        for dataset_id, spec in self.catalog.items():
            entry: dict[str, object] = {
                "id": dataset_id,
                "title": spec.title,
                "description": spec.description,
                "state": "missing",
                "progress": None,
                "error": "",
            }
            with self.state_lock:
                job = self.preparations.get(dataset_id)
            if self.prepared_scene(dataset_id) is not None:
                entry["state"] = "ready"
                entry["progress"] = {"phase": "ready", "done": 1, "total": 1}
            elif job is not None:
                step = job.progress
                entry["state"] = job.state
                entry["error"] = job.error
                if step is not None:
                    entry["progress"] = {
                        "phase": step.phase,
                        "done": step.done,
                        "total": step.total,
                    }
            scenes.append(entry)
        return {"current": self.default_dataset, "datasets": scenes}

    def prepare(self, dataset_id: str) -> str:
        """Start preparing `dataset_id` once (idempotent); its state now."""
        if self.prepared_scene(dataset_id) is not None:
            return "ready"
        with self.state_lock:
            job = self.preparations.get(dataset_id)
            if job is not None and job.state == "preparing":
                return job.state
            job = _Preparation()
            self.preparations[dataset_id] = job
        threading.Thread(target=self._prepare, args=(dataset_id, job), daemon=True).start()
        return job.state

    def _prepare(self, dataset_id: str, job: _Preparation) -> None:
        def report(step: PrepareProgress) -> None:
            job.progress = step

        try:
            prepared = ensure_dataset(
                self.catalog[dataset_id], self.cache_dir, fetch=self.fetch, progress=report
            )
        except Exception as exc:  # surfaced to the page via /datasets
            job.state, job.error = "error", str(exc)
            return
        with self.state_lock:
            self.prepared[dataset_id] = prepared
        job.state = "ready"


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
    prepared: PreparedDataset | None = None,
    *,
    catalog: Sequence[DatasetSpec] | None = None,
    cache_dir: Path | None = None,
    default_dataset: str | None = None,
    fetch: Callable[[str, Path], None] | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    fps: float | None = None,
    max_frames: int = 0,
    start_index: int = 0,
    with_rtabmap: bool = True,
    coral_model_dir: Path | None = None,
    coral_model: str = DEFAULT_PROFILE,
    rtabmap_mode: str = "live",
    sam_model: Path | str | None = None,
    sam_device: str | None = None,
    sam_label: str = "object",
    sam_source: VideoSamDetector | None = None,
    sam_detector: VideoSamDetector | None = None,
    sam_streamer: VideoSamStreamer | None = None,
    sam_fake: bool = False,
    history_db: Path | None = None,
    history_store: RunHistoryStore | None = None,
    backend_factory: Callable[[], SidecarRtabmapBackend | LiveSlamBackend] | None = None,
) -> ThreadingHTTPServer:
    """The demo HTTP server (not yet serving); caller serves/closes it.

    Every `catalog` scene (default: the registry) is offered; one not yet
    in `cache_dir` is prepared there the first time it is picked.
    `prepared`, when given, is served as the default scene.
    """
    specs = list(catalog) if catalog is not None else list(DATASETS.values())
    if prepared is not None and prepared.spec.dataset_id not in {s.dataset_id for s in specs}:
        specs.insert(0, prepared.spec)
    if not specs:
        raise ValueError("the demo needs at least one scene")
    if sam_source is not None and sam_detector is not None:
        raise ValueError("pass only one of sam_source and sam_detector")
    video_sam = sam_source if sam_source is not None else sam_detector
    if video_sam is not None and sam_streamer is not None:
        raise ValueError("pass only one of sam_source and sam_streamer")
    video_streamer = sam_streamer
    if sam_fake:
        if video_sam is not None or video_streamer is not None or sam_device is not None:
            raise ValueError("sam_fake replaces SAM: pass no other SAM source or device")
        video_sam = CentredBoxVideoSamDetector(sam_label)
    if video_sam is None and video_streamer is None and sam_device is not None:
        # Built eagerly so a missing model or GPU provider fails by
        # name at startup, not mid-stream. An `.onnx` model runs the
        # ONNX per-frame adapter; anything else (an HF id such as the
        # default facebook/sam3.1, a local .pt or its directory) runs
        # the real SAM 3.1 whole-video streamer on that device.
        from surmap.survey.sam3_torch import DEFAULT_SAM31_MODEL

        model_spec = str(sam_model) if sam_model is not None else DEFAULT_SAM31_MODEL
        if model_spec.endswith(".onnx"):
            from surmap.survey.sam3 import sam3_video_detector

            video_sam = sam3_video_detector(Path(model_spec), device=sam_device, label=sam_label)
        else:
            from surmap.survey.sam3_torch import sam31_video_streamer

            video_streamer = sam31_video_streamer(model_spec, device=sam_device, prompt=sam_label)
    elif video_sam is None and video_streamer is None and sam_model is not None:
        raise ValueError(
            "a SAM model without a device does nothing: pass sam_device "
            "(the launcher's --sam-device, e.g. cuda:0) alongside sam_model"
        )
    options: dict[str, object] = {
        "fps": fps,
        "max_frames": max_frames,
        "start_index": start_index,
        "with_rtabmap": with_rtabmap,
        "rtabmap_mode": rtabmap_mode,
        "detection_source": (
            coral_detection_source(coral_model_dir, coral_model) if coral_model_dir else None
        ),
        "sam_source": video_sam,
        "sam_streamer": video_streamer,
    }
    server = _DemoHttpServer((host, port), _DemoHandler)
    server.catalog = {spec.dataset_id: spec for spec in specs}
    server.default_dataset = default_dataset or (
        prepared.spec.dataset_id if prepared is not None else specs[0].dataset_id
    )
    if server.default_dataset not in server.catalog:
        raise ValueError(f"unknown default scene: {server.default_dataset}")
    server.cache_dir = cache_dir or (
        prepared.root.parent if prepared is not None else default_cache_dir()
    )
    if backend_factory is not None:
        options["backend_factory"] = backend_factory
    server.fetch = fetch
    server.history_store = history_store or RunHistoryStore(
        history_db or (server.cache_dir / "demo-history.db")
    )
    server.player_options = options
    server.sam_enabled = video_sam is not None or video_streamer is not None
    server.sam_label = sam_label
    server.stream_lock = threading.Lock()
    server.state_lock = threading.Lock()
    server.prepared = {prepared.spec.dataset_id: prepared} if prepared is not None else {}
    server.preparations = {}
    server.current = None
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

    def _send_json(self, status: int, body: dict[str, object]) -> None:
        self._send(status, "application/json", json.dumps(body).encode())

    def _scene(self, query: dict[str, list[str]]) -> str | None:
        """The requested scene id (default: the launcher's), or None if unknown."""
        dataset_id = query.get("dataset", [self.server.default_dataset])[0]
        return dataset_id if dataset_id in self.server.catalog else None

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path == "/health":
            self._send(200, "application/json", b'{"status": "ok"}')
            return
        if url.path == "/datasets":
            self._send_json(200, self.server.scene_listing())
            return
        if url.path == "/runs":
            self._send_json(200, {"runs": self.server.history_store.list_runs()})
            return
        if url.path.startswith("/runs/"):
            parts = [part for part in url.path.split("/") if part]
            store = self.server.history_store
            if len(parts) == 2:
                run = store.get_run(parts[1])
                if run is None:
                    self._send(404, "text/plain", b"unknown run")
                else:
                    self._send_json(200, {**run, "timeline": store.timeline(parts[1])})
                return
            if len(parts) == 3 and parts[2] == "snapshot":
                try:
                    seq = int(query.get("seq", ["0"])[0])
                except ValueError:
                    seq = -1
                snapshot = store.snapshot_at(parts[1], seq) if seq >= 0 else None
                if snapshot is None:
                    self._send(404, "text/plain", b"unknown moment")
                else:
                    self._send_json(200, snapshot)
                return
            self._send(404, "text/plain", b"not found")
            return
        if url.path in ("/", "/stream"):
            dataset_id = self._scene(query)
            if dataset_id is None:
                self._send(404, "text/plain", b"unknown scene")
            elif url.path == "/":
                spec = self.server.catalog[dataset_id]
                tuning = _page_tuning(spec)
                page = PAGE.format(
                    title=html.escape(spec.title),
                    description=html.escape(spec.description),
                    dataset_id=dataset_id,
                    sam_legend=(
                        " SAM (video) masks run in the separate pane below, at SAM's own rate."
                        if self.server.sam_enabled
                        else ""
                    ),
                    sam_pane=(
                        '<div class="sam-pane"><h2>SAM 3.1 (video) — own rate</h2>'
                        f'<canvas id="sam-view" width="{tuning["width"]}" '
                        f'height="{tuning["height"]}"></canvas>'
                        '<p class="legend" id="sam-status">SAM: waiting for '
                        "the first result…</p></div>"
                        if self.server.sam_enabled
                        else ""
                    ),
                    **tuning,
                )
                self._send(200, "text/html; charset=utf-8", page.encode())
            else:
                self._stream(dataset_id)
            return
        self._send(404, "text/plain", b"not found")

    def do_POST(self) -> None:
        url = urlsplit(self.path)
        if url.path == "/prepare":
            dataset_id = self._scene(parse_qs(url.query))
            if dataset_id is None:
                self._send(404, "text/plain", b"unknown scene")
                return
            self._send_json(202, {"state": self.server.prepare(dataset_id)})
            return
        if url.path == "/control":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                action = json.loads(self.rfile.read(length) or b"{}").get("action")
            except (ValueError, AttributeError):
                action = None
            controls = self.server.current
            if action not in ("pause", "resume"):
                self._send(400, "text/plain", b"action must be pause or resume")
            elif controls is None:
                self._send(409, "text/plain", b"nothing is playing")
            else:
                controls.pause() if action == "pause" else controls.resume()
                self._send_json(200, {"state": "paused" if controls.paused else "playing"})
            return
        self._send(404, "text/plain", b"not found")

    def _stream(self, dataset_id: str) -> None:
        prepared = self.server.prepared_scene(dataset_id)
        if prepared is None:
            self._send(409, "text/plain", b"scene not downloaded yet; POST /prepare first")
            return
        # The newest viewer takes over: stop the running player (its
        # finally tears the sidecar down), then wait for the lock.
        with self.server.state_lock:
            previous = self.server.current
        if previous is not None:
            previous.cancel()
        if not self.server.stream_lock.acquire(timeout=TAKEOVER_TIMEOUT_S):
            self._send(409, "text/plain", b"the running demo stream did not stop")
            return
        controls = PlaybackControls()
        with self.server.state_lock:
            self.server.current = controls
        store = self.server.history_store
        run_id = store.create_run(dataset_id, prepared.spec.title)
        completed = False
        last_frame_id = 0
        last_map: dict[str, object] = {}
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            run_chunk = (
                f"event: run\ndata: {json.dumps({'run_id': run_id, 'dataset_id': dataset_id})}\n\n"
            ).encode()
            self.wfile.write(run_chunk)
            self.wfile.flush()
            player = DemoPlayer(prepared, controls=controls, **self.server.player_options)  # type: ignore[arg-type]
            for event in player.events():
                payload = dict(event.data)
                if event.kind in ("frame", "sam") and event.jpeg:
                    payload["image_b64"] = base64.b64encode(event.jpeg).decode()
                if event.kind == "frame" and event.jpeg:
                    last_frame_id = int(str(event.data["frame_id"]))
                    overlay_raw = event.data["detections"]
                    camera_raw = event.data.get("camera")
                    store.record_frame(
                        run_id,
                        index=int(str(event.data["index"])),
                        frame_id=last_frame_id,
                        t_ns=int(str(event.data["t_ns"])),
                        jpeg=event.jpeg,
                        overlay=overlay_raw if isinstance(overlay_raw, list) else [],
                        camera=camera_raw if isinstance(camera_raw, dict) else None,
                    )
                elif event.kind == "map":
                    last_frame_id = int(str(event.data["frame_id"]))
                    last_map = dict(event.data)
                    _record_map(store, run_id, event.data, last_frame_id)
                elif event.kind == "detections":
                    objects_raw = event.data["objects"]
                    store.record_detections(
                        run_id,
                        frame_id=int(str(event.data["frame_id"])),
                        t_ns=int(str(event.data["t_ns"])),
                        objects=objects_raw if isinstance(objects_raw, list) else [],
                    )
                elif event.kind == "final":
                    # The final cloud keeps the last map's keyframe/odom stats.
                    _record_map(store, run_id, {**last_map, **event.data}, last_frame_id)
                    completed = True
                chunk = f"event: {event.kind}\ndata: {json.dumps(payload)}\n\n".encode()
                self.wfile.write(chunk)
                self.wfile.flush()
            completed = True
        except (BrokenPipeError, ConnectionResetError):
            pass  # viewer went away; the player's finally tears down
        finally:
            store.finish_run(run_id, "completed" if completed else "interrupted")
            with self.server.state_lock:
                if self.server.current is controls:
                    self.server.current = None
            self.server.stream_lock.release()


def _record_map(
    store: RunHistoryStore, run_id: str, data: dict[str, object], frame_id: int
) -> None:
    points = data.get("points")
    colors = data.get("point_colors")
    trajectory = data.get("trajectory_xy")
    extent = data.get("extent")
    store.record_map(
        run_id,
        frame_id=frame_id,
        points=points if isinstance(points, list) else [],
        colors=colors if isinstance(colors, list) else [],
        trajectory_xy=trajectory if isinstance(trajectory, list) else [],
        extent=extent if isinstance(extent, list) else [],
        cloud_points=int(str(data.get("cloud_points", 0))),
        keyframes=int(str(data.get("keyframes", 0))),
        odom_state=str(data.get("odom_state", "")),
    )


def page_title(prepared: PreparedDataset) -> str:
    """The test console page's heading for `prepared` (used by the launcher log)."""
    return f"SurMap Test Console — {prepared.spec.title}"
