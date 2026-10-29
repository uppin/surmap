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

With a SAM 2.1 segmenter (which needs the Coral detection source:
its tracked boxes are SAM's prompts), two more things happen:

- `segments`: live, best effort. A frame with Coral boxes is offered
  to a SAM worker thread; while the worker is busy, frames are
  skipped (counted), so SAM never slows playback. Results arrive as
  their own events keyed by `frame_id`, like `detections`.
- after the flush, each RTAB-Map keyframe with Coral boxes is
  segmented, the stereo points inside each mask are placed in the
  map by that keyframe's pose (`surmap.demo.fusion`), and `final`
  carries the per-label `semantic` layer. Only posed frames are
  placed; nothing is fed back into RTAB-Map.

Playback state is per connection and guarded: one viewer at a time.
"""

from __future__ import annotations

import base64
import html
import json
import math
import queue
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol

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
from surmap.demo.fusion import SemanticLayer, camera_to_base, points_in_mask
from surmap.detection.detector import CoralDetector, decode_rgb
from surmap.detection.profiles import DEFAULT_PROFILE, MODEL_PROFILES
from surmap.detection.source import CoralDetectionSource, DetectionSource
from surmap.slam.base import FrameResult
from surmap.slam.sidecar import SidecarRtabmapBackend
from surmap.survey.sam2 import BoxPrompt, Sam2Segment, sam2_segmenter
from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from surmap.types import Pose, StereoFramePair, Vec3

MAX_OVERLAY_POINTS = 600
MAX_MAP_POINTS = 4000
# How long playback's end waits for the last live SAM result.
SAM_DRAIN_TIMEOUT_S = 10.0


class SceneReconstructor(Protocol):
    def reconstruct(
        self, left: FrameImage, right: FrameImage, rig: StereoRig
    ) -> tuple[Vec3, ...]: ...


class BoxSegmenter(Protocol):
    def segment(
        self, rgb: NDArray[np.uint8], prompts: tuple[BoxPrompt, ...]
    ) -> tuple[Sam2Segment, ...]: ...


class BatchSlamBackend(Protocol):
    """The RTAB-Map sidecar as the player uses it: stage, then flush."""

    def process_frame(self, frame: StereoFramePair) -> FrameResult: ...

    def flush(self) -> list[FrameResult]: ...

    def trajectory(self) -> list[Pose]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class DemoEvent:
    kind: str  # "frame" | "status" | "final"
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


@dataclass(frozen=True)
class _SamJob:
    frame_id: int
    t_ns: int
    rgb: NDArray[np.uint8]
    prompts: tuple[BoxPrompt, ...]


@dataclass(frozen=True)
class _SamResult:
    frame_id: int
    t_ns: int
    segments: tuple[Sam2Segment, ...]
    ms: float


class _SamWorker:
    """One background SAM slot: offered frames are taken only when idle."""

    def __init__(self, segmenter: BoxSegmenter) -> None:
        self._segmenter = segmenter
        self._jobs: queue.Queue[_SamJob | None] = queue.Queue()
        self._results: queue.Queue[_SamResult | BaseException] = queue.Queue()
        self._idle = threading.Event()
        self._idle.set()
        self.analysed = 0
        self.dropped = 0
        self._thread = threading.Thread(target=self._run, name="surmap-demo-sam", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            started = time.monotonic()
            try:
                segments = self._segmenter.segment(job.rgb, job.prompts)
            except BaseException as exc:  # surfaced to the player on drain
                self._results.put(exc)
            else:
                ms = (time.monotonic() - started) * 1000.0
                self._results.put(_SamResult(job.frame_id, job.t_ns, segments, ms))
            finally:
                self._idle.set()

    def offer(self, job: _SamJob) -> bool:
        """Start `job` if the worker is idle; otherwise count a drop."""
        if not self._idle.is_set():
            self.dropped += 1
            return False
        self._idle.clear()
        self.analysed += 1
        self._jobs.put(job)
        return True

    def wait_idle(self, timeout: float) -> None:
        self._idle.wait(timeout)

    def drain(self) -> list[_SamResult]:
        results: list[_SamResult] = []
        while True:
            try:
                item = self._results.get_nowait()
            except queue.Empty:
                return results
            if isinstance(item, BaseException):
                raise item
            results.append(item)

    def close(self) -> None:
        self._jobs.put(None)
        self._thread.join(timeout=SAM_DRAIN_TIMEOUT_S)


def _segments_event(result: _SamResult, worker: _SamWorker) -> DemoEvent:
    return DemoEvent(
        "segments",
        {
            "frame_id": result.frame_id,
            "t_ns": result.t_ns,
            "ms": round(result.ms, 1),
            "analysed": worker.analysed,
            "dropped": worker.dropped,
            "objects": [
                {
                    "label": segment.detection.label,
                    "score": round(segment.detection.score, 2),
                    "track_id": segment.detection.track_id,
                    "polygon": [
                        [round(x, 1), round(y, 1)] for x, y in segment.detection.mask_polygon
                    ],
                }
                for segment in result.segments
            ],
        },
    )


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
        stereo: SceneReconstructor | None = None,
        detection_source: DetectionSource | None = None,
        segmenter: BoxSegmenter | None = None,
        slam_backend: Callable[[], BatchSlamBackend] | None = None,
    ) -> None:
        if fps <= 0:
            raise ValueError("fps must be positive")
        if segmenter is not None and detection_source is None:
            raise ValueError(
                "SAM 2.1 is prompted by Coral boxes: it needs a Coral detection source"
            )
        self._prepared = prepared
        self._native = load_calibration(prepared)
        self._calibration = self._native.scaled(DISPLAY_WIDTH, DISPLAY_HEIGHT)
        self._fps = fps
        self._max_frames = max_frames
        self._start_index = start_index
        self._with_rtabmap = with_rtabmap
        self._stereo: SceneReconstructor = stereo if stereo is not None else StereoReconstructor()
        self._detection_source = detection_source
        self._segmenter = segmenter
        self._slam_backend: Callable[[], BatchSlamBackend] = (
            slam_backend if slam_backend is not None else self._backend
        )

    def _backend(self) -> SidecarRtabmapBackend:
        prepared = self._prepared
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
        backend = self._slam_backend() if self._with_rtabmap else None
        worker = _SamWorker(self._segmenter) if self._segmenter is not None else None
        # Coral prompts per played frame, for segmenting RTAB-Map's
        # keyframes once the map exists (boxes only — no pixels kept).
        prompts_by_frame: dict[int, tuple[BoxPrompt, ...]] = {}
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
                    if worker is not None and tracked:
                        prompts = tuple(
                            BoxPrompt(d.label, d.score, d.box_xyxy, d.track_id) for d in tracked
                        )
                        if backend is not None:
                            prompts_by_frame[index + 1] = prompts
                        worker.offer(_SamJob(index + 1, t_ns, rgb, prompts))
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
                if worker is not None:
                    for sam_result in worker.drain():
                        yield _segments_event(sam_result, worker)
                # Server-side pacing: one frame interval per frame,
                # however long processing took — never a catch-up burst.
                remaining = 1.0 / self._fps - (time.monotonic() - frame_started)
                if remaining > 0:
                    time.sleep(remaining)
            if worker is not None:
                worker.wait_idle(SAM_DRAIN_TIMEOUT_S)
                for sam_result in worker.drain():
                    yield _segments_event(sam_result, worker)
            if backend is not None:
                yield DemoEvent(
                    "status", {"message": "Building the RTAB-Map map from all played frames…"}
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
                extra: dict[str, object] = {}
                if worker is not None and self._segmenter is not None:
                    keyframes = [
                        result
                        for result in results
                        if result.pose is not None and result.frame_id in prompts_by_frame
                    ]
                    layer = SemanticLayer(camera_to_base(prepared.sensor_yaml("cam0")))
                    for done, keyframe in enumerate(keyframes):
                        if done % 10 == 0:
                            yield DemoEvent(
                                "status",
                                {
                                    "message": f"Segmenting RTAB-Map keyframes with SAM 2.1… "
                                    f"{done} / {len(keyframes)}"
                                },
                            )
                        self._fuse_keyframe(
                            keyframe, prompts_by_frame[keyframe.frame_id], rig, layer
                        )
                    extra = {
                        "semantic": layer.summary(),
                        "sam": {
                            "live_analysed": worker.analysed,
                            "live_dropped": worker.dropped,
                            "keyframes_segmented": len(keyframes),
                        },
                    }
                yield DemoEvent(
                    "final",
                    {
                        **extra,
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
            if worker is not None:
                worker.close()
            if backend is not None:
                backend.close()

    def _fuse_keyframe(
        self,
        keyframe: FrameResult,
        prompts: tuple[BoxPrompt, ...],
        rig: StereoRig,
        layer: SemanticLayer,
    ) -> None:
        """Segment one posed keyframe; place its masked stereo points."""
        if self._segmenter is None or keyframe.pose is None:
            return
        left_jpeg = _display_jpeg(self._prepared, 0, keyframe.t_ns)
        right_jpeg = _display_jpeg(self._prepared, 1, keyframe.t_ns)
        left = FrameImage(DISPLAY_WIDTH, DISPLAY_HEIGHT, "mjpeg", left_jpeg)
        points = self._stereo.reconstruct(
            left, FrameImage(DISPLAY_WIDTH, DISPLAY_HEIGHT, "mjpeg", right_jpeg), rig
        )
        for segment in self._segmenter.segment(decode_rgb(left), prompts):
            claimed = points_in_mask(points, segment.mask, self._calibration)
            if claimed:
                layer.add(
                    segment.detection.label,
                    frame_id=keyframe.frame_id,
                    points_camera=claimed,
                    pose=keyframe.pose,
                )


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SurMap demo — {title}</title>
<style>
  body {{ margin: 0; background: #17191c; color: #e8eaed;
    font-family: "Segoe UI", system-ui, sans-serif; }}
  header {{ padding: 20px 28px 8px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; font-weight: 650; }}
  .sub {{ color: #9aa3ad; font-size: 13px; margin: 0; }}
  main {{ display: flex; gap: 20px; padding: 16px 28px 28px;
    flex-wrap: wrap; align-items: flex-start; }}
  .stage {{ flex: 1 1 640px; max-width: 880px; }}
  canvas#view {{ width: 100%; background: #000; border: 1px solid #34383e; display: block; }}
  aside {{ flex: 0 1 360px; min-width: 300px; }}
  h2 {{ font-size: 14px; margin: 18px 0 6px; font-weight: 650; }}
  h2:first-child {{ margin-top: 2px; }}
  .stat {{ font-size: 13px; color: #c3c9d1; line-height: 1.7; }}
  .stat b {{ color: #fff; font-weight: 650; }}
  canvas#map {{ background: #101215; border: 1px solid #34383e;
    width: 100%; display: block; }}
  .legend {{ font-size: 12px; color: #9aa3ad; }}
  .dot {{ display: inline-block; width: 9px; height: 9px;
    border-radius: 50%; vertical-align: -1px; }}
</style>
</head>
<body>
<header>
  <h1>SurMap demo — {title}</h1>
  <p class="sub">{description} Stereo scene points are overlaid live; the RTAB-Map map is built
  from the same frames and shown at the end.</p>
</header>
<main>
  <div class="stage">
    <canvas id="view" width="376" height="240"></canvas>
    <p class="legend">
      <span class="dot" style="background:#ff5a3c"></span> near &nbsp;
      <span class="dot" style="background:#ffb03a"></span> mid &nbsp;
      <span class="dot" style="background:#2fd4c4"></span> far
      &nbsp;— projected stereo detections, sized by depth.
      Yellow boxes: tracked objects from the separate detections stream.{sam_legend}
    </p>
  </div>
  <aside>
    <h2>Playback</h2>
    <div class="stat" id="playback">Connecting…</div>
    <h2>RTAB-Map</h2>
    <div class="stat" id="rtab">Waiting for playback to finish…</div>
    <canvas id="map" width="340" height="340"></canvas>
    <p class="legend">Top-down map: grey = RTAB-Map cloud (sampled), amber = camera trajectory,
      coloured = SAM 2.1 object points placed by RTAB-Map keyframe poses.</p>
    <div class="stat" id="semantic"></div>
  </aside>
</main>
<script>
const view = document.getElementById('view').getContext('2d');
const playback = document.getElementById('playback');
const rtab = document.getElementById('rtab');
let frames = 0, started = performance.now(), lastPoints = 0;
let latestDetections = null, latestSegments = null, samStats = '';
const labelColour = (label, alpha) => {{
  let hash = 0;
  for (const c of label) hash = (hash * 31 + c.charCodeAt(0)) % 360;
  return `hsla(${{hash}} 80% 60% / ${{alpha}})`;
}};
function drawSegments() {{
  if (!latestSegments) return;
  for (const object of latestSegments.objects) {{
    if (object.polygon.length < 3) continue;
    view.beginPath();
    object.polygon.forEach(([x, y], i) => i ? view.lineTo(x, y) : view.moveTo(x, y));
    view.closePath();
    view.fillStyle = labelColour(object.label, 0.35); view.fill();
    view.strokeStyle = labelColour(object.label, 0.9); view.lineWidth = 1; view.stroke();
  }}
}}
const source = new EventSource('/stream');
function drawBoxes() {{
  if (!latestDetections) return;
  view.strokeStyle = '#ffd23c'; view.lineWidth = 1.6;
  view.fillStyle = '#ffd23c'; view.font = '11px system-ui';
  for (const object of latestDetections.objects) {{
    const [x1, y1, x2, y2] = object.box;
    view.strokeRect(x1, y1, x2 - x1, y2 - y1);
    view.fillText(`${{object.label}} #${{object.track_id}}`, x1 + 2, Math.max(10, y1 - 3));
  }}
}}
source.addEventListener('segments', (event) => {{
  latestSegments = JSON.parse(event.data);
  samStats = `<br>SAM 2.1 masks <b>${{latestSegments.objects.length}}</b> `
    + `(${{latestSegments.ms}} ms; analysed ${{latestSegments.analysed}}, `
    + `skipped while busy ${{latestSegments.dropped}})`;
}});
source.addEventListener('detections', (event) => {{
  latestDetections = JSON.parse(event.data);
}});
source.addEventListener('frame', (event) => {{
  const data = JSON.parse(event.data);
  const image = new Image();
  image.onload = () => {{
    view.drawImage(image, 0, 0, 376, 240);
    for (const point of data.detections) {{
      const t = Math.min(1, Math.max(0, (point.d - 0.3) / 5.7));
      view.fillStyle = `hsl(${{180 - t * 180}} 85% 55%)`;
      view.beginPath();
      view.arc(point.x, point.y, point.d < 1.5 ? 2.2 : 1.4, 0, Math.PI * 2);
      view.fill();
    }}
    drawSegments();
    drawBoxes();
    URL.revokeObjectURL(image.src);
  }};
  image.src = 'data:image/jpeg;base64,' + data.image_b64;
  frames += 1; lastPoints = data.point_count;
  const fps = (frames / ((performance.now() - started) / 1000)).toFixed(1);
  playback.innerHTML = `Frame <b>${{data.index + 1}} / ${{data.total}}</b><br>`
    + `Stream rate <b>${{fps}} fps</b><br>`
    + `Stereo scene points this frame <b>${{data.point_count}}</b><br>`
    + `Overlay detections drawn <b>${{data.detections.length}}</b>` + samStats;
}});
source.addEventListener('status', (event) => {{
  rtab.textContent = JSON.parse(event.data).message;
}});
source.addEventListener('final', (event) => {{
  const data = JSON.parse(event.data);
  rtab.innerHTML = `Optimized poses <b>${{data.poses}}</b><br>`
    + `Trajectory travelled <b>${{data.travelled_m}} m</b><br>`
    + `Assembled cloud <b>${{data.cloud_points}} points</b> `
    + `(sample of ${{data.cloud_xy.length}} drawn)`;
  if (data.semantic) {{
    document.getElementById('semantic').innerHTML =
      `SAM 2.1 keyframes segmented <b>${{data.sam.keyframes_segmented}}</b><br>`
      + data.semantic.map(layer =>
        `<span class="dot" style="background:${{labelColour(layer.label, 1)}}"></span> `
        + `${{layer.label}} <b>${{layer.count}}</b> points in ${{layer.frames}} keyframes`
      ).join('<br>');
  }}
  drawMap(data);
  source.close();
}});
source.onerror = () => {{
  if (frames === 0) playback.textContent = 'Stream unavailable — is another viewer connected?';
}};
function drawMap(data) {{
  const canvas = document.getElementById('map');
  const ctx = canvas.getContext('2d');
  const semantic = data.semantic || [];
  const all = data.cloud_xy.concat(data.trajectory_xy);
  if (!all.length) return;
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const scale = Math.min(320 / Math.max(0.01, maxX - minX),
    320 / Math.max(0.01, maxY - minY));
  const px = p => [10 + (p[0] - minX) * scale, 330 - (p[1] - minY) * scale];
  ctx.fillStyle = '#8a929c';
  for (const point of data.cloud_xy) {{ const [x, y] = px(point); ctx.fillRect(x, y, 1.6, 1.6); }}
  for (const layer of semantic) {{
    ctx.fillStyle = labelColour(layer.label, 0.9);
    for (const point of layer.xy) {{
      const [x, y] = px(point); ctx.fillRect(x - 1, y - 1, 2.6, 2.6);
    }}
  }}
  ctx.strokeStyle = '#ffb03a'; ctx.lineWidth = 2; ctx.beginPath();
  data.trajectory_xy.forEach((point, i) => {{
    const [x, y] = px(point); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }});
  ctx.stroke();
}}
</script>
</body>
</html>
"""


class _DemoHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    prepared: PreparedDataset
    player_options: dict[str, object]
    stream_lock: threading.Lock
    sam_enabled: bool


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
    sam2_model_dir: Path | None = None,
    sam2_device: str = "auto",
) -> ThreadingHTTPServer:
    """The demo HTTP server (not yet serving); caller serves/closes it.

    `sam2_model_dir` enables SAM 2.1 (prompted by the Coral boxes, so
    it needs `coral_model_dir` too). The model loads once per server.
    """
    if sam2_model_dir is not None and coral_model_dir is None:
        raise ValueError("SAM 2.1 is prompted by Coral boxes: pass coral_model_dir too")
    options: dict[str, object] = {
        "fps": fps,
        "max_frames": max_frames,
        "start_index": start_index,
        "with_rtabmap": with_rtabmap,
        "detection_source": (
            coral_detection_source(coral_model_dir, coral_model) if coral_model_dir else None
        ),
        "segmenter": (
            sam2_segmenter(sam2_model_dir, device=sam2_device) if sam2_model_dir else None
        ),
    }
    server = _DemoHttpServer((host, port), _DemoHandler)
    server.prepared = prepared
    server.player_options = options
    server.stream_lock = threading.Lock()
    server.sam_enabled = sam2_model_dir is not None
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
            page = _PAGE.format(
                title=html.escape(self.server.prepared.spec.title),
                description=html.escape(self.server.prepared.spec.description),
                sam_legend=(
                    " Translucent shapes: SAM 2.1 masks, prompted by those boxes."
                    if self.server.sam_enabled
                    else ""
                ),
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
