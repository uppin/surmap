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
import shutil
import tempfile
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

from surmap.demo import run_archive
from surmap.demo.cloud_view import CLOUD_VIEW_PX as CLOUD_VIEW_PX
from surmap.demo.cloud_view import CloudPose as CloudPose
from surmap.demo.cloud_view import CloudViewer, FollowCamera, png_base64
from surmap.demo.cloud_view import render_cloud_view as render_cloud_view
from surmap.demo.datasets import (
    DATASETS,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    DatasetSpec,
    DemoCalibration,
    ImageModality,
    PreparedDataset,
    default_cache_dir,
    load_calibration,
    scaled_sensor_yaml,
)
from surmap.demo.dense_view import dense_depth_png
from surmap.demo.events import (
    DemoEvent as DemoEvent,
)
from surmap.demo.events import (
    RegionPlacer,
    SurfaceAssigner,
    dense_event,
    rig_event,
    sam_event,
    surface_layer,
)
from surmap.demo.history import RunHistoryStore
from surmap.demo.page import CM5_ASIDE, PAGE, RTAB_STAT
from surmap.demo.remote import (
    RemoteCm5Backend,
    RemoteDetectionSource,
    RemoteSamDetector,
)
from surmap.demo.remote import (
    fetch_capabilities as _fetch_capabilities,
)
from surmap.demo.runs import TAKEOVER_TIMEOUT_S as TAKEOVER_TIMEOUT_S
from surmap.demo.runs import DemoRunHost
from surmap.demo.runs import PlaybackControls as PlaybackControls
from surmap.demo.runs import _RunEngine as _RunEngine
from surmap.demo.sam_prompt import SamPromptPolicy, sam_pane
from surmap.demo.surface_render import MOVING_ALPHA as MOVING_ALPHA
from surmap.demo.surface_render import MOVING_COLOUR as MOVING_COLOUR
from surmap.demo.surface_render import SURFACE_ALPHA as SURFACE_ALPHA
from surmap.demo.surface_render import SURFACE_COLOURS as SURFACE_COLOURS
from surmap.demo.surface_render import SurfaceLayer
from surmap.demo.surface_render import surface_tint as surface_tint
from surmap.demo.surface_timeline import SurfaceTimelines
from surmap.detection.detector import CoralDetector, decode_rgb
from surmap.detection.profiles import DEFAULT_PROFILE, MODEL_PROFILES
from surmap.detection.source import CoralDetectionSource, DetectionSource
from surmap.detection.tracker import TrackedDetection
from surmap.slam.base import FrameResult
from surmap.slam.dense import DenseJournalSource, display_depth, region_rig_from_message
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
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[:, :, 0] = rgba[:, :, 1] = rgba[:, :, 2] = (
        np.round(mean).astype(np.uint8).reshape(size, size)
    )
    rgba[:, :, 3] = np.round(alpha).astype(np.uint8).reshape(size, size)
    return png_base64(rgba)


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


def _follow_camera(value: object) -> FollowCamera | None:
    """A journalled or snapshot floor camera, when it is one."""
    if not isinstance(value, dict) or not all(k in value for k in ("x", "z", "dx", "dz")):
        return None
    return {str(key): float(number) for key, number in value.items()}


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
        prompt: str | None = None,
    ) -> None:
        self._streamer = streamer
        self._frame_paths = frame_paths
        self._prompt = prompt
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
            for index, detections in self._streamer.stream(self._frame_paths, self._prompt):
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
    """The half-res JPEG for one frame, generated once and cached.

    Colour datasets keep colour (SAM segments the colour frame); grey
    datasets stay grey. The stereo/RTAB-Map path converts to grey itself.
    """
    width, height = prepared.spec.display_size
    target = prepared.root / f"display-{width}x{height}" / f"cam{channel}" / f"{t_ns}.jpg"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "RGB" if prepared.spec.modality is ImageModality.COLOR else "L"
        with Image.open(prepared.frame_path(channel, t_ns)) as frame:
            frame.resize((width, height)).convert(mode).save(target, format="JPEG", quality=85)
    return target.read_bytes()


def dense_depth_frame(
    store: RunHistoryStore, run_id: str, frame_id: int, stops: tuple[float, float, float]
) -> bytes | None:
    """RTAB-Map's dense depth of one frame of a run, as an overlay PNG (`surmap.demo.dense_view`).

    It is the disparity the sidecar journalled for that frame (a replay
    reads its recording's), never recomputed; None when RTAB-Map
    computed none for the frame.
    """
    root = store.root_run(run_id)
    journalled = store.rig(root)
    frame = store.dense_frame(root, frame_id)
    if journalled is None or frame is None:
        return None
    size_raw = journalled["display_size"]
    assert isinstance(size_raw, list) and len(size_raw) == 2
    size = (int(size_raw[0]), int(size_raw[1]))
    depth = display_depth(region_rig_from_message(journalled["rig"]), frame, size)
    return dense_depth_png(depth, size, stops, DEPTH_COLOURS)


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
        self.surfaces = SurfaceAssigner()  # the run's surfaces, assigned from regions
        self._stops = stops
        self._backend = backend
        self._calibration = calibration
        self._frames: deque[_HeldFrame] = deque()
        self._detections: list[DemoEvent] = []
        self._sam: list[DemoEvent] = []
        self._jpegs: dict[int, bytes] = {}
        self._shown = 0
        self.camera: FollowCamera | None = None  # the shown frame's, for the 3D pane's Follow

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
            self.camera = camera
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
                region = self._regions.region_event(event)
                yield region
                if (surface := self.surfaces.surface_event(region)) is not None:
                    yield surface

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


class _RateMeter:
    """Sliding-window rate of a cumulative counter, per second.

    Fed (time, counter) samples — here RTAB-Map's newest odometry
    frame — it reports how fast the counter advanced over the last
    window, decaying to zero when the counter stalls.
    """

    def __init__(self, window_s: float = 10.0) -> None:
        self._window_s = window_s
        self._samples: deque[tuple[float, int]] = deque()

    def sample(self, now: float, count: int) -> float:
        self._samples.append((now, count))
        cutoff = now - self._window_s
        while len(self._samples) >= 2 and self._samples[1][0] <= cutoff:
            self._samples.popleft()
        first_at, first_count = self._samples[0]
        span = now - first_at
        return (count - first_count) / span if span > 0.25 else 0.0


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
        sam_prompt: str | None = None,
        rtabmap_mode: str = "live",
        backend_factory: Callable[[], SidecarRtabmapBackend | LiveSlamBackend] | None = None,
        controls: PlaybackControls | None = None,
        cm5_host: str | None = None,
    ) -> None:
        self._cm5_host = cm5_host
        self._controls = controls if controls is not None else PlaybackControls()
        self._extent: FloorExtent | None = None
        self._cloud_bounds: tuple[NDArray[np.float32], NDArray[np.float32]] | None = None
        self._cloud_version = (-1, -1)  # (viewer pose / layers, surfaces) last drawn
        self._rtab_rate = _RateMeter()
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
        self._sam_prompt = sam_prompt
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

    def _map_event(
        self,
        backend: LiveSlamBackend,
        frame_id: int,
        surfaces: SurfaceLayer,
        camera: FollowCamera | None = None,
    ) -> DemoEvent:
        cloud = backend.map_cloud()
        points, colors = cloud_points(cloud)
        trajectory = backend.trajectory()
        if len(cloud.points):
            lo = cloud.points.min(axis=0)
            hi = cloud.points.max(axis=0)
            self._cloud_bounds = (
                (lo, hi)
                if self._cloud_bounds is None
                else (
                    np.minimum(self._cloud_bounds[0], lo),
                    np.maximum(self._cloud_bounds[1], hi),
                )
            )
        bounds = self._cloud_bounds or (
            np.zeros(3, dtype=np.float32),
            np.ones(3, dtype=np.float32),
        )
        return DemoEvent(
            "map",
            {
                "frame_id": frame_id,
                "points": points,
                "point_colors": colors,
                **self._controls.viewer.render_view(
                    cloud.points, cloud.colors, bounds, surfaces, camera
                ),
                **self._floor_plan(
                    cloud.points[:, [0, 2]], cloud.colors[:, 0], _floor_plane_trajectory(trajectory)
                ),
                "cloud_points": len(cloud.points),
                "keyframes": backend.keyframe_count,
                "rtab_fps": round(
                    self._rtab_rate.sample(time.monotonic(), backend.last_odom_frame), 1
                ),
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
        if self._cm5_host is not None:
            options = stream_backend_options(self._prepared)
            return RemoteCm5Backend(
                self._cm5_host,
                self._calibration,
                self._size,
                cam_yamls=(options.cam0_yaml, options.cam1_yaml),
                max_depth_m=options.max_depth_m,
            )
        prepared = self._prepared
        options = stream_backend_options(prepared)
        if self._rtabmap_mode == "live":
            return StreamingRtabmapBackend(
                cam0_yaml=options.cam0_yaml,
                cam1_yaml=options.cam1_yaml,
                width=options.width,
                height=options.height,
                max_depth_m=options.max_depth_m,
                dense_journal=True,  # every run is journalled for replay
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
            self._sam_source.reset(self._sam_prompt)  # a new playback is a new video
        stream_worker = (
            _SamStreamWorker(
                self._sam_streamer,
                [_display_jpeg_path(prepared, 0, t_ns) for t_ns in timestamps],
                [(index + 1, t_ns) for index, t_ns in enumerate(timestamps)],
                self._sam_prompt,
            )
            if self._sam_streamer is not None
            else None
        )
        live = backend if isinstance(backend, LiveSlamBackend) else None
        display = _Display(
            len(timestamps), live, calibration, prepared.spec.depth_stops_m, self._size
        )
        # Narrowed from `object`: mypy finds no overlap between the batch
        # sidecar in `backend`'s union and the protocol.
        found: object = backend
        journal = found if isinstance(found, DenseJournalSource) else None

        def released(*, final: bool = False) -> Iterator[DemoEvent]:
            """Released display events, then any dense frames the regions journalled."""
            yield from display.release(final=final)
            for frame in journal.poll_dense() if journal is not None else ():
                yield dense_event(frame)

        last_map_emit = 0.0
        try:
            if journal is not None and journal.region_rig is not None:
                yield rig_event(journal.region_rig, self._size)
            for index, t_ns in enumerate(timestamps):
                # Paused: no pairs reach SLAM and no new frames are shown,
                # but held frames keep resolving as their odometry lands.
                while self._controls.paused and not self._controls.cancelled:
                    if isinstance(backend, LiveSlamBackend):
                        backend.poll_updates()
                    yield from released()
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
                yield from released()
                if isinstance(backend, LiveSlamBackend):
                    now = time.monotonic()
                    version = (self._controls.cloud_version, display.surfaces.version)
                    if now - last_map_emit >= 0.33 or version != self._cloud_version:
                        last_map_emit = now
                        self._cloud_version = version
                        yield self._map_event(
                            backend, index + 1, display.surfaces.layer(), display.camera
                        )
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
            yield from released()
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
                yield from released(final=True)
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
                view: dict[str, str] = {"cloud_png": ""}
                if isinstance(backend, LiveSlamBackend):
                    live_cloud = backend.map_cloud()
                    final_points, final_colors = cloud_points(live_cloud)
                    final_count = len(live_cloud.points)
                    if len(live_cloud.points):
                        lo = live_cloud.points.min(axis=0)
                        hi = live_cloud.points.max(axis=0)
                        bounds = (
                            (lo, hi)
                            if self._cloud_bounds is None
                            else (
                                np.minimum(self._cloud_bounds[0], lo),
                                np.maximum(self._cloud_bounds[1], hi),
                            )
                        )
                        view = self._controls.viewer.render_view(
                            live_cloud.points,
                            live_cloud.colors,
                            bounds,
                            display.surfaces.layer(),
                            display.camera,
                        )
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
                        **view,
                        **plan,
                    },
                )
            yield from released(final=True)
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


class _DemoHttpServer(ThreadingHTTPServer, DemoRunHost):
    daemon_threads = True


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
    sam_label: str | None = None,
    sam_source: VideoSamDetector | None = None,
    sam_detector: VideoSamDetector | None = None,
    sam_streamer: VideoSamStreamer | None = None,
    sam_fake: bool = False,
    history_db: Path | None = None,
    history_store: RunHistoryStore | None = None,
    backend_factory: Callable[[], SidecarRtabmapBackend | LiveSlamBackend] | None = None,
    cm5_host: str | None = None,
    station_host: str | None = None,
) -> ThreadingHTTPServer:
    """The demo HTTP server (not yet serving); caller serves/closes it.

    Every `catalog` scene (default: the registry) is offered; one not yet
    in `cache_dir` is prepared there the first time it is picked.
    `prepared`, when given, is served as the default scene.
    `sam_label`, when given, replaces every scene's default SAM prompt.
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
    fixed_prompt: str | None = None
    if sam_fake:
        if video_sam is not None or video_streamer is not None or sam_device is not None:
            raise ValueError("sam_fake replaces SAM: pass no other SAM source or device")
        video_sam = CentredBoxVideoSamDetector(sam_label or "object")
    if video_sam is None and video_streamer is None and sam_device is not None:
        # Built eagerly so a missing model or GPU provider fails by
        # name at startup, not mid-stream. An `.onnx` model runs the
        # ONNX per-frame adapter; anything else (an HF id such as the
        # default facebook/sam3.1, a local .pt or its directory) runs
        # the real SAM 3.1 whole-video streamer on that device — except
        # on Apple's GPU, where only the image model runs, per frame.
        from surmap.survey import sam3_torch
        from surmap.survey.sam3 import parse_sam_device
        from surmap.survey.sam3_torch import DEFAULT_SAM31_MODEL

        model_spec = str(sam_model) if sam_model is not None else DEFAULT_SAM31_MODEL
        if model_spec.endswith(".onnx"):
            from surmap.survey.sam3 import sam3_video_detector

            # The export's concept was fixed when it was exported.
            fixed_prompt = sam_label or "object"
            video_sam = sam3_video_detector(Path(model_spec), device=sam_device, label=fixed_prompt)
        elif parse_sam_device(sam_device)[0] == "mps":
            video_sam = sam3_torch.sam31_torch_video_detector(
                model_spec, device=sam_device, prompt=sam_label or "object"
            )
        else:
            from surmap.survey.sam3_torch import sam31_video_streamer

            video_streamer = sam31_video_streamer(
                model_spec, device=sam_device, prompt=sam_label or "object"
            )
    elif video_sam is None and video_streamer is None and sam_model is not None:
        raise ValueError(
            "a SAM model without a device does nothing: pass sam_device "
            "(the launcher's --sam-device, e.g. cuda:0) alongside sam_model"
        )
    if cm5_host is not None and coral_model_dir is not None:
        raise ValueError("cm5_host replaces local Coral: pass no coral model dir")
    if station_host is not None and (
        video_sam is not None or video_streamer is not None or sam_device is not None
    ):
        raise ValueError("station_host replaces local SAM: pass no other SAM source or device")
    cm5_caps = _fetch_capabilities(cm5_host, "Cm5SurveyService") if cm5_host else None
    station_caps = _fetch_capabilities(station_host, "StationSamService") if station_host else None
    if station_host is not None and station_caps is not None and station_caps.sam_analysis:
        video_sam = RemoteSamDetector(station_host)
    options: dict[str, object] = {
        "fps": fps,
        "max_frames": max_frames,
        "start_index": start_index,
        "with_rtabmap": with_rtabmap and (cm5_host is None or cm5_caps is not None),
        "rtabmap_mode": rtabmap_mode,
        "detection_source": (
            coral_detection_source(coral_model_dir, coral_model) if coral_model_dir else None
        ),
        "sam_source": video_sam,
        "sam_streamer": video_streamer,
    }
    if cm5_host is not None:
        options["cm5_host"] = cm5_host
        if cm5_caps is not None and cm5_caps.detections:
            options["detection_source"] = RemoteDetectionSource(cm5_host)
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
    server.cm5_enabled = cm5_host is None or cm5_caps is not None
    station_execution = ""
    if station_caps is not None and station_caps.sam_analysis:
        device = station_caps.device
        kind = (
            "GPU"
            if device.lower().startswith("cuda") or "cuda" in station_caps.provider.lower()
            else "CPU"
        )
        detail = f"{station_caps.provider} · {device}" if device else station_caps.provider
        station_execution = f"{kind} · {detail}" if detail else kind
    server.station_execution = station_execution
    server.sam_enabled = video_sam is not None or video_streamer is not None
    server.sam_prompts = SamPromptPolicy(override=sam_label, fixed=fixed_prompt)
    server.run_lock = threading.Lock()
    server.state_lock = threading.Lock()
    server.prepared = {prepared.spec.dataset_id: prepared} if prepared is not None else {}
    server.preparations = {}
    server.current = None
    server.cloud_viewer = CloudViewer()
    server.surface_timelines = SurfaceTimelines(server.history_store)
    server.run_engine = None
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

    def _send_export(self, run_id: str) -> None:
        """The run as a `.surmaprun` download (`surmap.demo.run_archive`)."""
        store = self.server.history_store
        run = store.get_run(run_id)
        if run is None:
            self._send(404, "text/plain", b"unknown run")
            return
        with tempfile.TemporaryDirectory(dir=store.path.parent) as scratch:
            out = Path(scratch) / run_archive.archive_name(str(run["dataset_id"]), run_id)
            try:
                run_archive.export_from(store, run_id, out)
            except run_archive.RunNotExportable as exc:
                self._send(409, "text/plain", str(exc).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(out.stat().st_size))
            self.send_header("Content-Disposition", f'attachment; filename="{out.name}"')
            self.end_headers()
            with out.open("rb") as archive:
                shutil.copyfileobj(archive, self.wfile, 1 << 20)

    def _receive_import(self) -> None:
        """Import an uploaded `.surmaprun` file into the history."""
        store = self.server.history_store
        remaining = int(self.headers.get("Content-Length") or 0)
        with tempfile.TemporaryDirectory(dir=store.path.parent) as scratch:
            upload = Path(scratch) / f"upload{run_archive.SUFFIX}"
            with upload.open("wb") as archive:
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 1 << 20))
                    if not chunk:
                        break
                    archive.write(chunk)
                    remaining -= len(chunk)
            try:
                report = run_archive.import_into(store, upload)
            except run_archive.NotARunArchive as exc:
                self._send(400, "text/plain", str(exc).encode())
                return
        self._send_json(200, {"imported": report.imported, "skipped": report.skipped})

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
            if len(parts) == 3 and parts[2] == "export":
                self._send_export(parts[1])
                return
            if len(parts) == 3 and parts[2] == "dense-depth":
                self._dense_depth(parts[1], query)
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
                    # A journalled run's moment shows today's surface logic, not the
                    # surfaces recorded with the logic it ran with (surface_timeline.py).
                    timeline = self.server.surface_timelines.get(parts[1])
                    if timeline is not None:
                        frame_id = int(str(snapshot["frame_id"]))
                        snapshot["surfaces"], snapshot["surface_tracks"] = timeline.at(frame_id)
                    cloud = snapshot.get("cloud")
                    if isinstance(cloud, dict) and isinstance(cloud.get("points"), list):
                        snap_points = np.array(cloud["points"], dtype=np.float32).reshape(-1, 3)
                        snap_colors = np.array(cloud.get("colors") or [], dtype=np.uint8)
                        if len(snap_points) and len(snap_colors) == len(snap_points):
                            cloud.update(
                                self.server.cloud_viewer.render_view(
                                    snap_points,
                                    snap_colors.reshape(-1, 3),
                                    (snap_points.min(axis=0), snap_points.max(axis=0)),
                                    surface_layer(snapshot.get("surfaces")),
                                    _follow_camera(snapshot.get("camera")),
                                )
                            )
                    self._send_json(200, snapshot)
                return
            self._send(404, "text/plain", b"not found")
            return
        if url.path == "/stream" and "rebuild_rtabmap" in query:
            self._rebuild_rtabmap(query["rebuild_rtabmap"][0])
            return
        if url.path == "/stream" and "replay" in query:
            self._replay(
                query["replay"][0],
                query.get("speed", ["1"])[0],
                record=query.get("record", ["1"])[0] != "0",
            )
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
                    cm5_aside=CM5_ASIDE if self.server.cm5_enabled else "",
                    rtab_stat=RTAB_STAT if self.server.cm5_enabled else "",
                    sam_pane=sam_pane(
                        dataset_id,
                        self.server.sam_prompt(dataset_id, query.get("prompt", [None])[0]),
                        fixed=self.server.sam_prompts.fixed is not None,
                        size=spec.display_size,
                        execution=self.server.station_execution,
                    ),
                    **tuning,
                )
                self._send(200, "text/html; charset=utf-8", page.encode())
            else:
                self._stream(dataset_id, query.get("prompt", [None])[0])
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
        if url.path == "/runs/import":
            self._receive_import()
            return
        if url.path == "/control":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                action = body.get("action")
            except (ValueError, AttributeError):
                body, action = {}, None
            controls = self.server.current
            cloud_actions = (
                "cloud_orbit",
                "cloud_zoom",
                "cloud_pan",
                "cloud_reset",
                "cloud_surfaces",
                "cloud_follow",
            )
            if action not in ("pause", "resume", *cloud_actions):
                self._send(400, "text/plain", b"action must be pause, resume or a cloud_* action")
            elif action in ("pause", "resume"):
                if controls is None:
                    self._send(409, "text/plain", b"nothing is playing")
                else:
                    controls.pause() if action == "pause" else controls.resume()
                    self._send_json(200, {"state": "paused" if controls.paused else "playing"})
            else:
                # The view is the session's: it moves with or without a run,
                # and answers with the last scene drawn from the new pose.
                viewer = self.server.cloud_viewer
                if action == "cloud_orbit":
                    pose = viewer.orbit(
                        float(body.get("d_azimuth") or 0.0), float(body.get("d_elevation") or 0.0)
                    )
                elif action == "cloud_zoom":
                    pose = viewer.zoom(float(body.get("factor") or 1.0))
                elif action == "cloud_pan":
                    pose = viewer.pan(float(body.get("dx") or 0.0), float(body.get("dz") or 0.0))
                elif action == "cloud_surfaces":
                    visible = body.get("visible")
                    viewer.set_surfaces_visible(visible if isinstance(visible, bool) else None)
                    pose = viewer.pose()
                elif action == "cloud_follow":
                    viewer.set_follow(body.get("follow") is not False)
                    pose = viewer.pose()
                else:
                    pose = viewer.reset()
                self._send_json(
                    200,
                    {
                        "azimuth": pose.azimuth,
                        "elevation": pose.elevation,
                        "zoom": pose.zoom,
                        "pan_x": pose.pan_x,
                        "pan_z": pose.pan_z,
                        "surfaces_visible": viewer.surfaces_visible,
                        "follow": viewer.follow,
                        "camera": viewer.camera,
                        **(viewer.rerender_view() or {"cloud_png": None, "cloud_ids_png": None}),
                    },
                )
            return
        self._send(404, "text/plain", b"not found")

    def _dense_depth(self, run_id: str, query: dict[str, list[str]]) -> None:
        """RTAB-Map's dense depth overlay of one frame of a run, by its frame id."""
        store = self.server.history_store
        run = store.get_run(run_id)
        try:
            frame_id = int(query.get("frame_id", [""])[0])
        except ValueError:
            frame_id = -1
        spec = None if run is None else self.server.catalog.get(str(run["dataset_id"]))
        png = (
            None if spec is None else dense_depth_frame(store, run_id, frame_id, spec.depth_stops_m)
        )
        if png is None:
            self._send(404, "text/plain", b"no RTAB-Map dense depth for this frame")
            return
        self._send(200, "image/png", png)

    def _stream(self, dataset_id: str, requested_prompt: str | None) -> None:
        prepared = self.server.prepared_scene(dataset_id)
        if prepared is None:
            self._send(409, "text/plain", b"scene not downloaded yet; POST /prepare first")
            return
        # The run lives server-side (see _RunEngine); this connection
        # only renders what it publishes. The newest viewer takes the
        # run over: the previous engine is cancelled and its
        # subscribers ended.
        engine = self.server.start_run(
            prepared, self.server.sam_prompt(dataset_id, requested_prompt)
        )
        self._serve(engine)

    def _rebuild_rtabmap(self, run_id: str) -> None:
        """A new live RTAB-Map run of `run_id`'s scene, with `run_id`'s SAM masks."""
        run = self.server.history_store.get_run(run_id)
        if run is None or not run["replayable"]:
            self._send(404, "text/plain", b"no journalled run to rebuild")
            return
        prepared = self.server.prepared_scene(str(run["dataset_id"]))
        if prepared is None:
            self._send(409, "text/plain", b"scene not downloaded yet; POST /prepare first")
            return
        self._serve(self.server.start_run(prepared, None, sam_from=run_id))

    def _replay(self, run_id: str, speed_raw: str, *, record: bool = True) -> None:
        run = self.server.history_store.get_run(run_id)
        if run is None or not run["replayable"]:
            self._send(404, "text/plain", b"no journalled run to replay")
            return
        try:
            speed = max(0.0, float(speed_raw))
        except ValueError:
            speed = 1.0
        self._serve(self.server.start_replay(run_id, speed, record))

    def _serve(self, engine: _RunEngine | None) -> None:
        """Stream a run's published events to this viewer as SSE."""
        if engine is None:
            self._send(409, "text/plain", b"the running demo stream did not stop")
            return
        subscriber = engine.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            while True:
                event = subscriber.get()
                if event is None:
                    # Said explicitly: a stream that just closes makes the
                    # browser's EventSource reconnect, starting a new run
                    # that takes this one back from whoever took it over.
                    reason = "taken over" if engine.controls.cancelled else "finished"
                    ended = json.dumps({"reason": reason})
                    self.wfile.write(f"event: ended\ndata: {ended}\n\n".encode())
                    self.wfile.flush()
                    break
                payload = dict(event.data)
                if event.kind in ("frame", "sam") and event.jpeg:
                    payload["image_b64"] = base64.b64encode(event.jpeg).decode()
                chunk = f"event: {event.kind}\ndata: {json.dumps(payload)}\n\n".encode()
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # viewer went away; the run carries on server-side
        finally:
            engine.unsubscribe(subscriber)


def page_title(prepared: PreparedDataset) -> str:
    """The test console page's heading for `prepared` (used by the launcher log)."""
    return f"SurMap Test Console — {prepared.spec.title}"
