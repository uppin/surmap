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
"""

from __future__ import annotations

import http.client
import io
import json
import socket
import struct
import threading
from collections.abc import Iterator
from typing import Any

import numpy as np
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import DataReceived, StreamEnded, StreamReset, WindowUpdated
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.datasets import DemoCalibration
from surmap.detection.tracker import TrackedDetection
from surmap.slam.base import FrameResult
from surmap.slam.stream_protocol import Keypoint, MapUpdate, OdomUpdate, Rectification
from surmap.slam.streaming import MapCloud
from surmap.survey.sam import RawFrame, SamDetection
from surmap.survey.v1 import survey_pb2
from surmap.types import Pose, StereoFramePair, Vec3

_MAX_CLOUD_POINTS = 300_000


def _frame_message(message: Any) -> bytes:
    payload: bytes = message.SerializeToString()
    return struct.pack(">BI", 0, len(payload)) + payload


def _read_payloads(raw: bytes) -> list[bytes]:
    payloads: list[bytes] = []
    offset = 0
    while offset < len(raw):
        flag, length = struct.unpack(">BI", raw[offset : offset + 5])
        payload = raw[offset + 5 : offset + 5 + length]
        if flag == 2:
            trailer = json.loads(payload or b"{}")
            error = trailer.get("error") if isinstance(trailer, dict) else None
            if error:
                raise RuntimeError(f"wire error: {error.get('message', error)}")
            break
        payloads.append(payload)
        offset += 5 + length
    return payloads


def _exchange(address: str, path: str, requests: list[Any], timeout: float = 60.0) -> list[bytes]:
    """One send-all/read-all bidi exchange (config + frames in, replies out)."""
    connection = http.client.HTTPConnection(address, timeout=timeout)
    try:
        connection.request(
            "POST",
            path,
            body=b"".join(_frame_message(request) for request in requests),
            headers={"content-type": "application/connect+proto"},
        )
        return _read_payloads(connection.getresponse().read())
    finally:
        connection.close()


def _unary(address: str, path: str, request: Any, timeout: float) -> bytes:
    connection = http.client.HTTPConnection(address, timeout=timeout)
    try:
        connection.request(
            "POST",
            path,
            body=request.SerializeToString(),
            headers={"content-type": "application/proto"},
        )
        response = connection.getresponse()
        body = response.read()
        if response.status != 200:
            raise RuntimeError(f"unary {path} answered HTTP {response.status}")
        return body
    finally:
        connection.close()


def fetch_capabilities(
    address: str, service: str, timeout: float = 3.0
) -> survey_pb2.Capabilities | None:
    """A host's reported capabilities, or None when it does not answer."""
    try:
        raw = _unary(
            address,
            f"/surmap.survey.v1.{service}/GetCapabilities",
            survey_pb2.CapabilitiesRequest(),
            timeout,
        )
        return survey_pb2.Capabilities.FromString(raw)
    except Exception:
        return None


class _SurveyStream:
    """One long-lived `StreamSurvey` exchange over HTTP/2 (h2c).

    The Connect sync/async clients cannot stream a request body
    against the repo's Hypercorn host (their body writer fails
    before the handler runs), so the survey stream — the one demo
    flow that must interleave sends and receives — speaks h2c
    directly: frames go out as they are played, point batches are
    parsed off the same connection by the reader thread.
    """

    def __init__(self, address: str) -> None:
        host, _, port = address.rpartition(":")
        self._socket = socket.create_connection((host, int(port)), timeout=60.0)
        self._socket.settimeout(None)
        config = H2Configuration(client_side=True, header_encoding="utf-8")
        self._conn = H2Connection(config=config)
        self._lock = threading.Lock()
        self._window_ready = threading.Condition(self._lock)
        self._stream_id = 1
        self._buffer = bytearray()
        self._ended = False
        with self._lock:
            self._conn.initiate_connection()
            self._conn.send_headers(
                self._stream_id,
                [
                    (":method", "POST"),
                    (":path", "/surmap.survey.v1.Cm5SurveyService/StreamSurvey"),
                    (":scheme", "http"),
                    (":authority", address),
                    ("content-type", "application/connect+proto"),
                    ("te", "trailers"),
                ],
            )
            self._conn.increment_flow_control_window(1 << 24)
            self._conn.increment_flow_control_window(1 << 24, stream_id=self._stream_id)
            self._flush()

    def _flush(self) -> None:
        data = self._conn.data_to_send()
        if data:
            self._socket.sendall(data)

    def send(self, message: survey_pb2.Cm5Request) -> None:
        framed = _frame_message(message)
        offset = 0
        with self._window_ready:
            while offset < len(framed):
                window = self._conn.local_flow_control_window(self._stream_id)
                if window <= 0:
                    self._window_ready.wait(timeout=60.0)
                    continue
                chunk = framed[offset : offset + min(window, 16384)]
                self._conn.send_data(self._stream_id, chunk)
                self._flush()
                offset += len(chunk)

    def finish(self) -> None:
        with self._lock:
            self._conn.end_stream(self._stream_id)
            self._flush()

    def responses(self) -> Iterator[survey_pb2.Cm5Response]:
        while not self._ended:
            chunk = self._socket.recv(65536)
            if not chunk:
                return
            with self._window_ready:
                events = self._conn.receive_data(chunk)
                self._flush()
                for event in events:
                    if isinstance(event, DataReceived):
                        self._buffer += event.data
                        self._conn.acknowledge_received_data(
                            event.flow_controlled_length, event.stream_id
                        )
                    elif isinstance(event, WindowUpdated):
                        self._window_ready.notify_all()
                    elif isinstance(event, StreamEnded):
                        self._ended = True
                    elif isinstance(event, StreamReset):
                        raise RuntimeError(f"survey stream reset: {event.error_code}")
                self._flush()
            yield from self._drain()

    def _drain(self) -> Iterator[survey_pb2.Cm5Response]:
        while len(self._buffer) >= 5:
            flag, length = struct.unpack(">BI", bytes(self._buffer[:5]))
            if len(self._buffer) < 5 + length:
                return
            payload = bytes(self._buffer[5 : 5 + length])
            del self._buffer[: 5 + length]
            if flag == 2:
                trailer = json.loads(payload or b"{}")
                error = trailer.get("error") if isinstance(trailer, dict) else None
                if error:
                    raise RuntimeError(f"wire error: {error.get('message', error)}")
                self._ended = True
                return
            yield survey_pb2.Cm5Response.FromString(payload)

    def close(self) -> None:
        try:
            self._socket.close()
        except OSError:
            pass


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
    ) -> None:
        self._address = address
        self._calibration = calibration
        self._size = size
        self._cam_yamls = cam_yamls
        self._max_depth_m = max_depth_m
        self._stream: _SurveyStream | None = None
        self._reader_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._scene: list[Vec3] = []
        self._scene_frames: set[int] = set()
        self._odom: dict[int, OdomUpdate] = {}
        self._rectification: Rectification | None = None
        self._error: BaseException | None = None
        self._finished = False

    def _ensure_stream(self) -> _SurveyStream:
        if self._stream is not None:
            return self._stream
        stream = _SurveyStream(self._address)
        calibration = self._calibration
        stream.send(
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
        self._stream = stream
        self._reader_thread = threading.Thread(target=self._read, daemon=True)
        self._reader_thread.start()
        return stream

    def _read(self) -> None:
        assert self._stream is not None
        try:
            for response in self._stream.responses():
                kind = response.WhichOneof("kind")
                if kind == "odom":
                    self._store_odom(response.odom)
                    continue
                if kind != "points":
                    continue
                batch = response.points
                if batch.designation != 1:
                    continue
                with self._lock:
                    self._scene_frames.add(batch.frame_id)
                    self._scene.extend(Vec3(point.x, point.y, point.z) for point in batch.points)
                    if len(self._scene) > _MAX_CLOUD_POINTS:
                        del self._scene[: len(self._scene) - _MAX_CLOUD_POINTS]
        except BaseException as exc:  # surfaced on the playback thread
            with self._lock:
                self._error = exc

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        stream = self._ensure_stream()
        width, height = self._size
        for channel, data in ((0, frame.left_data), (1, frame.right_data)):
            stream.send(
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
        if self._stream is not None and not self._finished:
            self._finished = True
            self._stream.finish()
            if self._reader_thread is not None:
                self._reader_thread.join(timeout=120)
        with self._lock:
            if self._error is not None:
                raise self._error
        return []

    def close(self) -> None:
        if self._stream is not None:
            try:
                self.flush()
            except Exception:
                pass
            self._stream.close()

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

    def __init__(self, address: str) -> None:
        self._address = address

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
        payloads = _exchange(
            self._address, "/surmap.survey.v1.Cm5SurveyService/StreamDetections", requests
        )
        tracked: list[TrackedDetection] = []
        for payload in payloads:
            detections = survey_pb2.DetectionResponse.FromString(payload).detections
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

    def __init__(self, address: str, prompt: str = "object") -> None:
        self._address = address
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
        payloads = _exchange(
            self._address, "/surmap.survey.v1.StationSamService/StreamAnalysis", requests
        )
        detections: list[SamDetection] = []
        for payload in payloads:
            frame_result = survey_pb2.StationResponse.FromString(payload).detections
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
        pass
