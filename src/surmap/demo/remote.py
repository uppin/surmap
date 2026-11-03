"""Wire clients for the demo's remote CM5/Station pipelines.

The demo page can run against the deployed servers instead of its
in-process pipelines. These adapters sit behind the demo's existing
seams, so the playback/session code does not change shape:

- `RemoteCm5Backend` — a `LiveSlamBackend` over `StreamSurvey`:
  played pairs go to the CM5; its designated point batches, per-frame
  odometry (pose + tracked keypoints, for the video overlay) and the
  growing map snapshot come back on the same stream. Designation 1
  accumulates into the demo cloud.
- `RemoteDetectionSource` — a `DetectionSource` over
  `StreamDetections` (one short exchange per frame; the tracker state
  lives server-side, so track ids persist across exchanges).
- `RemoteSamDetector` — a `VideoSamDetector` over `StreamAnalysis`
  (one short exchange per frame) with client-side box association
  for persistent track ids, mirroring `Sam3VideoDetector`.
- `fetch_capabilities` — the unary `GetCapabilities` on either
  service, or None when the host does not answer; the demo renders
  only the panes a host reports.

Every adapter talks to its server over one `SurveyConnection` (Connect
over a WebSocket, asyncio), opened on first use and kept for the
adapter's life. The demo's seams are synchronous, so each adapter runs
its connection on an event loop of its own in a background thread.
An address is anything `connect_url` accepts (`host:port`, `ws(s)://`,
`http(s)://`); `token` is the server's bearer token, if it has one.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import io
import threading
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any, TypeVar

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.datasets import DemoCalibration
from surmap.detection.tracker import TrackedDetection
from surmap.slam.base import FrameResult
from surmap.slam.stream_protocol import Keypoint, MapUpdate, OdomUpdate, Rectification
from surmap.slam.streaming import MapCloud
from surmap.survey.sam import RawFrame, SamDetection
from surmap.survey.v1 import survey_pb2
from surmap.survey.ws_client import SurveyConnection, SurveyService
from surmap.types import Pose, StereoFramePair, Vec3

_MAX_CLOUD_POINTS = 300_000

# How long one exchange (a frame's detections or analysis) may take.
_EXCHANGE_TIMEOUT_S = 60.0
# How long closing waits for the WebSocket close handshake before dropping the socket.
_CLOSE_TIMEOUT_S = 5.0

T = TypeVar("T")


class _Link:
    """One `SurveyConnection` on a private event loop thread, for synchronous callers."""

    def __init__(self, address: str, token: str | None) -> None:
        self._address = address
        self._token = token
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._serve_loop, daemon=True)
        self._thread.start()
        self._connection: SurveyConnection | None = None
        self._closing: asyncio.Event | None = None
        self._holder: asyncio.Future[None] | None = None

    def _serve_loop(self) -> None:
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def run(self, coro: Coroutine[Any, Any, T], timeout_s: float = _EXCHANGE_TIMEOUT_S) -> T:
        """Run `coro` on the link's loop and wait for its result."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout_s)

    def submit(self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """Start `coro` on the link's loop without waiting for it."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def call_soon(self, callback: Callable[[], None]) -> None:
        self._loop.call_soon_threadsafe(callback)

    async def connection(self) -> SurveyConnection:
        """The link's connection, opened on first use (call on the link's loop)."""
        if self._connection is None:
            opened: asyncio.Future[SurveyConnection] = self._loop.create_future()
            self._closing = asyncio.Event()
            self._holder = self._loop.create_task(self._hold(opened, self._closing))
            self._connection = await opened
        return self._connection

    async def _hold(self, opened: asyncio.Future[SurveyConnection], closing: asyncio.Event) -> None:
        try:
            async with SurveyConnection.open(self._address, token=self._token) as connection:
                opened.set_result(connection)
                await closing.wait()
        except BaseException as error:
            if not opened.done():
                opened.set_exception(error)
            raise

    def close(self) -> None:
        """Close the connection and stop the loop, without waiting: the close handshake
        finishes on the link's own thread, so a caller on the server's loop cannot block it."""
        if not self._loop.is_closed() and self._thread.is_alive():
            asyncio.run_coroutine_threadsafe(self._shut_down(), self._loop)

    async def _shut_down(self) -> None:
        if self._closing is not None and self._holder is not None:
            self._closing.set()
            try:
                await asyncio.wait_for(asyncio.shield(self._holder), _CLOSE_TIMEOUT_S)
            except BaseException:
                pass
        current = asyncio.current_task()
        others = [task for task in asyncio.all_tasks() if task is not current]
        for task in others:
            task.cancel()
        await asyncio.gather(*others, return_exceptions=True)
        self._loop.stop()


def fetch_capabilities(
    address: str, service: SurveyService, timeout: float = 3.0, token: str | None = None
) -> survey_pb2.Capabilities | None:
    """A host's reported capabilities, or None when it does not answer."""

    async def ask() -> survey_pb2.Capabilities:
        async with SurveyConnection.open(address, token=token, open_timeout_s=timeout) as link:
            return await asyncio.wait_for(link.capabilities(service), timeout)

    try:
        return asyncio.run(ask())
    except Exception:
        return None


async def _single(*messages: T) -> AsyncIterator[T]:
    for message in messages:
        yield message


def _jpeg_bytes(rgb: NDArray[np.uint8]) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


class RemoteCm5Backend:
    """A `LiveSlamBackend` whose map is a CM5 server's survey output."""

    def __init__(
        self,
        address: str,
        calibration: DemoCalibration,
        size: tuple[int, int],
        cam_yamls: tuple[str, str] | None = None,
        max_depth_m: float = 0.0,
        token: str | None = None,
    ) -> None:
        self._address = address
        self._token = token
        self._calibration = calibration
        self._size = size
        self._cam_yamls = cam_yamls
        self._max_depth_m = max_depth_m
        self._link: _Link | None = None
        self._requests: asyncio.Queue[survey_pb2.Cm5Request | None] | None = None
        self._survey: concurrent.futures.Future[None] | None = None
        self._lock = threading.Lock()
        self._scene: list[Vec3] = []
        self._scene_frames: set[int] = set()
        self._odom: dict[int, OdomUpdate] = {}
        self._rectification: Rectification | None = None
        self._error: BaseException | None = None
        self._finished = False

    def _ensure_stream(self) -> None:
        if self._link is not None:
            return
        link = _Link(self._address, self._token)

        async def new_queue() -> asyncio.Queue[survey_pb2.Cm5Request | None]:
            return asyncio.Queue()

        self._requests = link.run(new_queue())
        self._link = link
        calibration = self._calibration
        self._send(
            survey_pb2.Cm5Request(
                config=survey_pb2.Cm5StreamConfig(
                    calibration=survey_pb2.StereoCalibration(
                        calibration_id="demo-remote",
                        focal_length_px=calibration.fx,
                        baseline_m=calibration.baseline_m,
                        cx=calibration.cx,
                        cy=calibration.cy,
                        width=self._size[0],
                        height=self._size[1],
                    ),
                    video_channels=[],
                    cam0_yaml=self._cam_yamls[0] if self._cam_yamls else "",
                    cam1_yaml=self._cam_yamls[1] if self._cam_yamls else "",
                    max_depth_m=self._max_depth_m,
                )
            )
        )
        self._survey = link.submit(self._run(link, self._requests))

    def _send(self, message: survey_pb2.Cm5Request | None) -> None:
        """Queue `message` on the survey stream; `None` ends the stream."""
        assert self._link is not None and self._requests is not None
        queue = self._requests
        self._link.call_soon(lambda: queue.put_nowait(message))

    async def _run(self, link: _Link, queue: asyncio.Queue[survey_pb2.Cm5Request | None]) -> None:
        async def requests() -> AsyncIterator[survey_pb2.Cm5Request]:
            while (message := await queue.get()) is not None:
                yield message

        try:
            connection = await link.connection()
            async for response in connection.stream_survey(requests()):
                self._receive(response)
        except BaseException as exc:  # surfaced on the playback thread
            with self._lock:
                self._error = exc

    def _receive(self, response: survey_pb2.Cm5Response) -> None:
        kind = response.WhichOneof("kind")
        if kind == "odom":
            self._store_odom(response.odom)
            return
        if kind != "points":
            return
        batch = response.points
        if batch.designation != 1:
            return
        with self._lock:
            self._scene_frames.add(batch.frame_id)
            self._scene.extend(Vec3(point.x, point.y, point.z) for point in batch.points)
            if len(self._scene) > _MAX_CLOUD_POINTS:
                del self._scene[: len(self._scene) - _MAX_CLOUD_POINTS]

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self._ensure_stream()
        width, height = self._size
        for channel, data in ((0, frame.left_data), (1, frame.right_data)):
            self._send(
                survey_pb2.Cm5Request(
                    frame=survey_pb2.RawVideoFrame(
                        frame_id=frame.frame_id,
                        t_ns=frame.t_ns,
                        channel=channel,
                        width=width,
                        height=height,
                        encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                        data=data,
                    )
                )
            )
        return FrameResult(frame.frame_id, frame.t_ns, None, ())

    def poll_updates(self) -> list[MapUpdate]:
        with self._lock:
            if self._error is not None:
                raise self._error
        return []

    def map_snapshot(self) -> tuple[Vec3, ...]:
        with self._lock:
            return tuple(self._scene)

    def map_cloud(self) -> MapCloud:
        with self._lock:
            points = np.asarray(
                [(point.x, point.y, point.z) for point in self._scene], dtype=np.float32
            ).reshape(-1, 3)
        colors = np.full((len(points), 3), 190, dtype=np.uint8)
        return MapCloud(points=points, colors=colors)

    def _store_odom(self, odom: survey_pb2.OdomUpdateOut) -> None:
        def pose(point: Any, orientation: Any) -> Pose | None:
            if point is None:
                return None
            values = tuple(float(v) for v in orientation)
            quad = (
                (values[0], values[1], values[2], values[3])
                if len(values) == 4
                else (0.0, 0.0, 0.0, 1.0)
            )
            return Pose(Vec3(point.x, point.y, point.z), quad)

        update = OdomUpdate(
            frame_id=int(odom.frame_id),
            t_ns=int(odom.t_ns),
            pose=pose(
                odom.position if odom.HasField("position") else None,
                odom.orientation_xyzw,
            ),
            lost=False,
            ms=0.0,
            keypoints=tuple(
                Keypoint(int(k.word_id), float(k.u), float(k.v), float(k.depth))
                for k in odom.keypoints
            ),
            map_pose=pose(
                odom.map_position if odom.HasField("map_position") else None,
                odom.map_orientation_xyzw,
            ),
        )
        with self._lock:
            self._odom[update.frame_id] = update
            while len(self._odom) > 8192:
                del self._odom[next(iter(self._odom))]
            if odom.HasField("rectification") and self._rectification is None:
                rect = odom.rectification

                def four(values: Any) -> tuple[float, float, float, float]:
                    items = tuple(float(v) for v in values)
                    return (items[0], items[1], items[2], items[3])

                self._rectification = Rectification(
                    rotation=tuple(float(v) for v in rect.rotation),
                    rectified=four(rect.rectified),
                    raw=four(rect.raw),
                    distortion=four(rect.distortion),
                )

    def frame_odometry(self, frame_id: int) -> OdomUpdate | None:
        with self._lock:
            return self._odom.get(frame_id)

    def trajectory(self) -> list[Pose]:
        with self._lock:
            updates = [self._odom[fid] for fid in sorted(self._odom)]
        return [pose for update in updates if (pose := update.map_pose or update.pose) is not None]

    def flush(self) -> list[FrameResult]:
        if self._survey is not None and not self._finished:
            self._finished = True
            self._send(None)
            try:
                self._survey.result(timeout=120)
            except concurrent.futures.TimeoutError:
                pass
        with self._lock:
            if self._error is not None:
                raise self._error
        return []

    def close(self) -> None:
        if self._link is not None:
            try:
                self.flush()
            except Exception:
                pass
            self._link.close()

    @property
    def dropped_frames(self) -> int:
        return 0

    @property
    def odom_state(self) -> str:
        return "remote"

    @property
    def last_odom_frame(self) -> int:
        with self._lock:
            return max(self._odom, default=max(self._scene_frames, default=0))

    @property
    def keyframe_count(self) -> int:
        with self._lock:
            return len(self._scene_frames)

    @property
    def rectification(self) -> Rectification | None:
        with self._lock:
            return self._rectification


class RemoteDetectionSource:
    """A `DetectionSource` served by a CM5's `StreamDetections`."""

    def __init__(self, address: str, token: str | None = None) -> None:
        self._link = _Link(address, token)

    def detect_tracked(self, frame_id: int, rgb: NDArray[np.uint8]) -> tuple[TrackedDetection, ...]:
        height, width = int(rgb.shape[0]), int(rgb.shape[1])
        requests = [
            survey_pb2.Cm5Request(
                config=survey_pb2.Cm5StreamConfig(
                    calibration=survey_pb2.StereoCalibration(calibration_id="demo-remote"),
                    video_channels=[],
                )
            ),
            survey_pb2.Cm5Request(
                frame=survey_pb2.RawVideoFrame(
                    frame_id=frame_id,
                    t_ns=frame_id,
                    channel=0,
                    width=width,
                    height=height,
                    encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                    data=_jpeg_bytes(rgb),
                )
            ),
        ]

        async def exchange() -> list[survey_pb2.DetectionResponse]:
            connection = await self._link.connection()
            return [r async for r in connection.stream_detections(_single(*requests))]

        tracked: list[TrackedDetection] = []
        for response in self._link.run(exchange()):
            detections = response.detections
            if detections.frame_id != frame_id:
                continue
            for detection in detections.detections:
                box = detection.box
                tracked.append(
                    TrackedDetection(
                        label=detection.label,
                        score=detection.score,
                        box_xyxy=(box.x_min, box.y_min, box.x_max, box.y_max),
                        track_id=detection.track_id if detection.HasField("track_id") else -1,
                        frame_id=frame_id,
                    )
                )
        return tuple(tracked)

    def close(self) -> None:
        self._link.close()


def _iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    x_min, y_min = max(a[0], b[0]), max(a[1], b[1])
    x_max, y_max = min(a[2], b[2]), min(a[3], b[3])
    if x_max <= x_min or y_max <= y_min:
        return 0.0
    intersection = (x_max - x_min) * (y_max - y_min)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return intersection / max(area_a + area_b - intersection, 1e-9)


class RemoteSamDetector:
    """A `VideoSamDetector` served by a Station's `StreamAnalysis`.

    Each frame is one short exchange; persistent ids come from
    client-side box association (IoU >= 0.3), mirroring
    `Sam3VideoDetector`. The station's reported provider/device are
    kept for the page's SAM status.
    """

    def __init__(self, address: str, prompt: str = "object", token: str | None = None) -> None:
        self._link = _Link(address, token)
        self._prompt = prompt
        self.provider = ""
        self.device = ""
        self._tracks: dict[int, tuple[float, float, float, float]] = {}
        self._next_track_id = 1

    def reset(self, prompt: str | None = None) -> None:
        if prompt is not None:
            self._prompt = prompt
        self._tracks = {}
        self._next_track_id = 1

    def track(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        requests = [
            survey_pb2.StationRequest(
                config=survey_pb2.StationStreamConfig(
                    calibration=survey_pb2.StereoCalibration(calibration_id="demo-remote"),
                    concept_prompts=[self._prompt],
                    analysis_mode=survey_pb2.ANALYSIS_MODE_EVERY_FRAME,
                )
            ),
            survey_pb2.StationRequest(
                frame=survey_pb2.RawVideoFrame(
                    frame_id=frame.frame_id,
                    t_ns=frame.t_ns,
                    channel=0,
                    width=frame.width,
                    height=frame.height,
                    encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                    data=frame.data,
                )
            ),
        ]

        async def exchange() -> list[survey_pb2.StationResponse]:
            connection = await self._link.connection()
            return [r async for r in connection.stream_analysis(_single(*requests))]

        detections: list[SamDetection] = []
        for response in self._link.run(exchange()):
            frame_result = response.detections
            if frame_result.frame_id != frame.frame_id:
                continue
            if frame_result.provider:
                self.provider, self.device = frame_result.provider, frame_result.device
            for detection in frame_result.detections:
                box = detection.box
                detections.append(
                    SamDetection(
                        label=detection.label,
                        score=detection.score,
                        box_xyxy=(box.x_min, box.y_min, box.x_max, box.y_max),
                        mask_polygon=tuple((point.x, point.y) for point in detection.mask_polygon),
                    )
                )
        return self._associate(detections)

    def _associate(self, detections: list[SamDetection]) -> tuple[SamDetection, ...]:
        matched: dict[int, tuple[float, float, float, float]] = {}
        output: list[SamDetection] = []
        for detection in detections:
            best_id, best_iou = -1, 0.3
            for track_id, box in self._tracks.items():
                if track_id in matched:
                    continue
                overlap = _iou(detection.box_xyxy, box)
                if overlap >= best_iou:
                    best_id, best_iou = track_id, overlap
            if best_id < 0:
                best_id = self._next_track_id
                self._next_track_id += 1
            matched[best_id] = detection.box_xyxy
            output.append(
                SamDetection(
                    detection.label,
                    detection.score,
                    detection.box_xyxy,
                    detection.mask_polygon,
                    best_id,
                )
            )
        self._tracks = matched
        return tuple(output)

    def close(self) -> None:
        self._link.close()
