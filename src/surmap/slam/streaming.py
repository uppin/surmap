"""Streaming RTAB-Map backend: long-lived sidecar over stdin/stdout.

`process_frame` never waits on RTAB-Map: it enqueues the pair for a
writer thread (bounded, drop-oldest) and returns the newest odometry
pose already known. A reader thread applies odom/keyframe/graph
messages to host-side state, so `map_snapshot()` re-places keyframe
points whenever the optimized graph moves them.
"""

from __future__ import annotations

import io
import os
import queue
import subprocess
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.slam.base import FrameResult
from surmap.slam.sidecar import SHARED_CONTAINER_ENV, SidecarError, _subprocess_runner
from surmap.slam.stream_protocol import (
    NEUTRAL_GREY,
    ErrorUpdate,
    GraphUpdate,
    KeyframeUpdate,
    MapUpdate,
    OdomUpdate,
    Ready,
    Rectification,
    decode_server_line,
    encode_hello,
    encode_pair,
)
from surmap.types import Pose, StereoFramePair, Vec3

STREAM_IMAGE_REPO = "surmap/rtabmap-stream"

# The pinned RTAB-Map image is published for amd64 only; arm64 hosts
# (Apple Silicon) build and run it emulated. A no-op on amd64 hosts.
PINNED_PLATFORM = "linux/amd64"

# Stored per keyframe so map_snapshot() stays cheap on long runs:
# the snapshot re-transforms stored points on every poll, so an
# unbounded per-keyframe cloud makes it quadratic in run length.
MAX_STORED_POINTS_PER_KEYFRAME = 1000

# Odom/ResetCountdown: RTAB-Map's default (0) never resets a lost
# odometry, so one dropout ends tracking for the rest of a run (measured
# on NTU VIRAL sbs_01: 719/1200 frames lost; 0/3325 with 1).
DEFAULT_RTABMAP_PARAMS = {"Rtabmap/DetectionRate": "2", "Odom/ResetCountdown": "1"}

# Per-frame odometry kept for display (~10 s at 20 Hz): a display holds a
# frame back only until its odometry arrives, never this long.
FRAME_ODOMETRY_KEPT = 200


def stream_image_tag(source_dir: Path | None = None) -> str:
    """Content-hash tag for the derived streaming image."""
    import hashlib

    root = source_dir or Path(__file__).resolve().parents[3] / "deploy" / "rtabmap-stream"
    digest = hashlib.sha256()
    for name in sorted(os.listdir(root)):
        path = root / name
        if path.is_file():
            digest.update(name.encode())
            digest.update(path.read_bytes())
    return f"{STREAM_IMAGE_REPO}:{digest.hexdigest()[:12]}"


def stream_build_argv(tag: str, source_dir: Path) -> list[str]:
    """`docker build` command for the derived streaming image."""
    return ["docker", "build", "--platform", PINNED_PLATFORM, "-t", tag, str(source_dir)]


@dataclass(frozen=True)
class MapCloud:
    """The live map in the map frame: (N, 3) float32 points, (N, 3) uint8 RGB."""

    points: NDArray[np.float32]
    colors: NDArray[np.uint8]


@dataclass(frozen=True)
class _Keyframe:
    """One stored keyframe: its odometry pose and capped local points."""

    node_id: int
    pose: Pose
    points: NDArray[np.float32]
    colors: NDArray[np.uint8]

    @staticmethod
    def of(update: KeyframeUpdate) -> _Keyframe:
        points = np.array([(p.x, p.y, p.z) for p in update.points_local], dtype=np.float32).reshape(
            -1, 3
        )
        colors = np.array(update.colors or [NEUTRAL_GREY] * len(points), dtype=np.uint8).reshape(
            -1, 3
        )
        if len(points) > MAX_STORED_POINTS_PER_KEYFRAME:
            pick = (
                np.arange(MAX_STORED_POINTS_PER_KEYFRAME)
                * len(points)
                // MAX_STORED_POINTS_PER_KEYFRAME
            )
            points, colors = points[pick], colors[pick]
        return _Keyframe(update.node_id, update.pose, points, colors)


class StreamProcess(Protocol):
    def write(self, data: bytes) -> None: ...
    def close_stdin(self) -> None: ...
    def readline(self) -> bytes: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int | None: ...


class _PopenProcess:
    def __init__(self, argv: list[str]) -> None:
        self._proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    def write(self, data: bytes) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(data)
        self._proc.stdin.flush()

    def close_stdin(self) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.close()

    def readline(self) -> bytes:
        assert self._proc.stdout is not None
        return self._proc.stdout.readline()

    def terminate(self) -> None:
        self._proc.terminate()

    def wait(self, timeout: float | None = None) -> int | None:
        try:
            return self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def stderr_tail(self) -> str:
        try:
            assert self._proc.stderr is not None
            return self._proc.stderr.read()[-2000:].decode(errors="replace")
        except Exception:
            return ""


def _default_factory(argv: list[str]) -> StreamProcess:
    return _PopenProcess(argv)


def _to_gray8(frame: StereoFramePair, channel: int, width: int, height: int) -> bytes:
    """Raw 8-bit grey pixels at the sidecar's configured size (no re-encode)."""
    data = frame.left_data if channel == 0 else frame.right_data
    if data:
        source: io.BytesIO | Path = io.BytesIO(data)
    else:
        ref = frame.left_ref if channel == 0 else frame.right_ref
        source = Path(ref)
        if not source.is_file():
            raise SidecarError(
                f"frame {frame.frame_id} channel {channel} carries no image bytes "
                f"and ref {ref!r} is not a readable file"
            )
    with Image.open(source) as image:
        gray = image.convert("L")
        if gray.size != (width, height):
            gray = gray.resize((width, height), Image.Resampling.BILINEAR)
        return gray.tobytes()


def pose_rotation(pose: Pose) -> NDArray[np.float32]:
    """3x3 rotation matrix of a pose's unit quaternion."""
    x, y, z, w = pose.orientation_xyzw
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float32,
    )


def _place(pose: Pose, points: NDArray[np.float32]) -> NDArray[np.float32]:
    """Keyframe-local points into the map frame."""
    translation = np.array([pose.position.x, pose.position.y, pose.position.z], dtype=np.float32)
    placed: NDArray[np.float32] = points @ pose_rotation(pose).T + translation
    return placed


class StreamingRtabmapBackend:
    """`SlamBackend` backed by the long-lived `surmap-rtabmap-stream` process."""

    def __init__(
        self,
        *,
        cam0_yaml: str,
        cam1_yaml: str,
        width: int = 376,
        height: int = 240,
        params: dict[str, str] | None = None,
        process_factory: Callable[[list[str]], StreamProcess] | None = None,
        image: str | None = None,
        runner: Callable[[list[str]], None] | None = None,
        queue_size: int = 4,
        flush_timeout: float = 120.0,
        max_depth_m: float = 6.0,
    ) -> None:
        if os.environ.get(SHARED_CONTAINER_ENV, "").strip():
            raise SidecarError(
                "StreamingRtabmapBackend does not support shared-container mode "
                f"({SHARED_CONTAINER_ENV} is set); unset it or use the batch sidecar"
            )
        self._width, self._height = width, height
        self._flush_timeout = flush_timeout
        self._runner = runner if runner is not None else _subprocess_runner
        self._image = image or stream_image_tag()
        self._instance_id = uuid.uuid4().hex[:12]
        self._container_name = f"surmap-rtabmap-stream-{self._instance_id}"
        self._live_containers: list[str] = [self._container_name]
        self.closed = False
        self._dropped = 0
        self._dropped_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._odom: dict[int, Pose] = {}
        self._odom_order: list[int] = []
        self._lost_frames: set[int] = set()
        self._keyframes: dict[int, _Keyframe] = {}
        self._graph: dict[int, Pose] = {}
        # node_id -> (pose used, map-frame points); a keyframe is
        # re-placed only when its optimized pose actually moves.
        self._placed_cache: dict[int, tuple[Pose, NDArray[np.float32]]] = {}
        self._frames: list[StereoFramePair] = []
        self._updates: queue.Queue[MapUpdate] = queue.Queue()
        self._in_queue: queue.Queue[tuple[StereoFramePair, bytes, bytes] | None] = queue.Queue(
            maxsize=max(1, queue_size)
        )
        self._error: str | None = None
        self._rectification: Rectification | None = None
        # Newest odometry per frame, keypoints included, for the display.
        self._frame_odometry: dict[int, OdomUpdate] = {}
        self._final = threading.Event()
        self._ready = threading.Event()
        argv = [
            "docker",
            "run",
            "-i",
            "--rm",
            "--name",
            self._container_name,
            "--platform",
            PINNED_PLATFORM,
            self._image,
        ]
        for key, value in sorted((params or DEFAULT_RTABMAP_PARAMS).items()):
            argv += ["--Param", f"{key}={value}"]
        self._process = (process_factory or _default_factory)(argv)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._writer = threading.Thread(target=self._write_loop, daemon=True)
        self._reader.start()
        self._writer.start()
        try:
            self._process.write(
                encode_hello(cam0_yaml, cam1_yaml, width, height, params or {}, max_depth_m)
            )
        except Exception as exc:
            raise SidecarError(f"streaming sidecar hello failed: {exc}") from exc
        if not self._ready.wait(timeout=30):
            raise SidecarError("streaming sidecar did not become ready")
        if self._error is not None:
            raise SidecarError(f"streaming sidecar error: {self._error}")

    @property
    def live_containers(self) -> tuple[str, ...]:
        return tuple(self._live_containers)

    @property
    def container_name(self) -> str:
        return self._container_name

    @property
    def keyframe_count(self) -> int:
        with self._state_lock:
            return len(self._keyframes)

    @property
    def dropped_frames(self) -> int:
        with self._dropped_lock:
            return self._dropped

    @property
    def last_input_frame(self) -> int:
        return self._frames[-1].frame_id if self._frames else 0

    @property
    def last_odom_frame(self) -> int:
        with self._state_lock:
            return self._odom_order[-1] if self._odom_order else 0

    @property
    def odom_state(self) -> str:
        with self._state_lock:
            if self._lost_frames and (
                not self._odom_order or max(self._lost_frames) > self._odom_order[-1]
            ):
                return "lost"
            return "tracking" if self._odom_order else "tracking"

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        if self.closed:
            raise SidecarError("cannot process frames after close()")
        if self._error is not None:
            raise SidecarError(f"streaming sidecar error: {self._error}")
        left = _to_gray8(frame, 0, self._width, self._height)
        right = _to_gray8(frame, 1, self._width, self._height)
        self._frames.append(frame)
        item = (frame, left, right)
        try:
            self._in_queue.put_nowait(item)
        except queue.Full:
            try:
                self._in_queue.get_nowait()
                with self._dropped_lock:
                    self._dropped += 1
            except queue.Empty:
                pass
            self._in_queue.put_nowait(item)
        with self._state_lock:
            pose = self._odom.get(frame.frame_id)
        return FrameResult(frame.frame_id, frame.t_ns, pose, ())

    def _write_loop(self) -> None:
        while True:
            item = self._in_queue.get()
            if item is None:
                try:
                    self._process.close_stdin()
                except Exception:
                    pass
                return
            frame, left, right = item
            try:
                self._process.write(
                    encode_pair(
                        frame.frame_id,
                        frame.t_ns,
                        self._width,
                        self._height,
                        left,
                        right,
                        encoding="gray8",
                    )
                )
            except Exception as exc:  # process died
                self._error = str(exc)
                return

    def _read_loop(self) -> None:
        while True:
            try:
                line = self._process.readline()
            except Exception:
                return
            if not line:
                return
            try:
                message = decode_server_line(line)
            except Exception as exc:
                self._error = str(exc)
                self._ready.set()  # a bad hello (e.g. version mismatch) fails fast
                continue
            if isinstance(message, Ready):
                self._rectification = message.rectification
                self._ready.set()
            elif isinstance(message, ErrorUpdate):
                self._error = message.message
                self._ready.set()
            else:
                with self._state_lock:
                    if isinstance(message, OdomUpdate):
                        self._frame_odometry[message.frame_id] = message
                        while len(self._frame_odometry) > FRAME_ODOMETRY_KEPT:
                            del self._frame_odometry[next(iter(self._frame_odometry))]
                        if message.pose is not None:
                            if message.frame_id not in self._odom:
                                self._odom_order.append(message.frame_id)
                            self._odom[message.frame_id] = message.pose
                        elif message.lost:
                            self._lost_frames.add(message.frame_id)
                    elif isinstance(message, KeyframeUpdate):
                        self._keyframes[message.node_id] = _Keyframe.of(message)
                    elif isinstance(message, GraphUpdate):
                        if message.poses:
                            # The graph is authoritative: a node it no
                            # longer holds (merged or discarded by
                            # RTAB-Map) leaves the map.
                            self._graph = dict(message.poses)
                            for node_id in [n for n in self._keyframes if n not in self._graph]:
                                del self._keyframes[node_id]
                        if message.final:
                            self._final.set()
                self._updates.put(message)
                if isinstance(message, GraphUpdate) and message.final:
                    self._final.set()

    def poll_updates(self) -> list[MapUpdate]:
        drained: list[MapUpdate] = []
        while True:
            try:
                drained.append(self._updates.get_nowait())
            except queue.Empty:
                return drained

    @property
    def rectification(self) -> Rectification | None:
        return self._rectification

    def frame_odometry(self, frame_id: int) -> OdomUpdate | None:
        """That frame's odometry (pose and tracked keypoints), once it arrived."""
        with self._state_lock:
            return self._frame_odometry.get(frame_id)

    def map_snapshot(self) -> tuple[Vec3, ...]:
        return tuple(Vec3(x, y, z) for x, y, z in self.map_cloud().points.tolist())

    def map_cloud(self) -> MapCloud:
        with self._state_lock:
            keyframes = list(self._keyframes.values())
            graph = dict(self._graph)
        for node_id in [n for n in self._placed_cache if n not in self._keyframes]:
            del self._placed_cache[node_id]
        placed: list[NDArray[np.float32]] = []
        for kf in keyframes:
            pose = graph.get(kf.node_id, kf.pose)
            cached = self._placed_cache.get(kf.node_id)
            if cached is None or cached[0] != pose:
                cached = (pose, _place(pose, kf.points))
                self._placed_cache[kf.node_id] = cached
            placed.append(cached[1])
        if not keyframes:
            return MapCloud(np.zeros((0, 3), np.float32), np.zeros((0, 3), np.uint8))
        return MapCloud(np.concatenate(placed), np.concatenate([kf.colors for kf in keyframes]))

    def trajectory(self) -> list[Pose]:
        with self._state_lock:
            if self._graph:
                return [self._graph[node_id] for node_id in sorted(self._graph)]
            return [self._odom[fid] for fid in self._odom_order if fid in self._odom]

    def flush(self) -> list[FrameResult]:
        # Sentinel closes stdin after queued pairs are written.
        self._in_queue.put(None)
        if not self._final.wait(timeout=self._flush_timeout):
            raise SidecarError("streaming sidecar flush timed out waiting for the final graph")
        if self._error is not None:
            raise SidecarError(f"streaming sidecar error: {self._error}")
        self.poll_updates()
        cloud = self.map_snapshot()
        with self._state_lock:
            odom = dict(self._odom)
        results: list[FrameResult] = []
        for frame in sorted(self._frames, key=lambda f: f.t_ns):
            pose = odom.get(frame.frame_id)
            if pose is not None:
                results.append(FrameResult(frame.frame_id, frame.t_ns, pose, ()))
        if results and cloud:
            last = results[-1]
            results[-1] = FrameResult(last.frame_id, last.t_ns, last.pose, cloud)
        return results

    def close(self) -> None:
        if self.closed and not self._live_containers:
            return
        self.closed = True
        try:
            self._in_queue.put_nowait(None)
        except Exception:
            pass
        try:
            self._process.terminate()
        except Exception:
            pass
        for thread in (self._writer, self._reader):
            thread.join(timeout=2)
        for name in list(self._live_containers):
            try:
                self._runner(["docker", "rm", "-f", name])
            except Exception:
                pass
            else:
                self._live_containers.remove(name)
