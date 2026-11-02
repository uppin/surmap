"""Demo tests: registry/cache logic, overlay projection, and a real
HTTP smoke of the demo server (started and closed in the test).
"""

import base64
import hashlib
import io
import json
import math
import threading
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.datasets import (
    DATASETS,
    DatasetSpec,
    PreparedDataset,
    ensure_dataset,
    load_calibration,
    scaled_sensor_yaml,
)
from surmap.demo.server import (
    DemoEvent,
    DemoPlayer,
    FloorExtent,
    cloud_points,
    depth_colour,
    make_demo_server,
    project_overlay,
    rectified_to_raw,
)
from surmap.detection.tracker import TrackedDetection
from surmap.slam.base import FrameResult
from surmap.slam.stream_protocol import Keypoint, MapUpdate, OdomUpdate, Rectification
from surmap.slam.streaming import MapCloud
from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from surmap.types import Pose, StereoFramePair, Vec3

CAM0_YAML = """sensor_type: camera
T_BS:
  cols: 4
  rows: 4
  data: [0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, -0.05,
         0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 1.0]
rate_hz: 20
resolution: [752, 480]
camera_model: pinhole
intrinsics: [458.0, 457.0, 367.0, 248.0]
distortion_model: radial-tangential
distortion_coefficients: [0.0, 0.0, 0.0, 0.0]
"""
CAM1_YAML = CAM0_YAML.replace("0.0, -0.05,", "0.0, 0.06,")


class FakeLiveBackend:
    """Live backend double: a fixed coloured map cloud, trajectory and newest pose."""

    def __init__(
        self,
        cloud: list[tuple[tuple[float, float, float], tuple[int, int, int]]] | None = None,
        trajectory: list[Pose] | None = None,
        odometry: dict[int, OdomUpdate] | None = None,
        odometry_lag: int = 0,
    ) -> None:
        entries = cloud if cloud is not None else [((1.0, 2.0, 0.0), (128, 128, 128))]
        self.cloud = MapCloud(
            np.array([xyz for xyz, _ in entries], dtype=np.float32).reshape(-1, 3),
            np.array([rgb for _, rgb in entries], dtype=np.uint8).reshape(-1, 3),
        )
        self._trajectory = trajectory if trajectory is not None else [Pose(Vec3(0.1, 0.0, 0.0))]
        self._odometry = odometry or {}
        self._odometry_lag = odometry_lag
        self._arrived_through = 0
        self.rectification: Rectification | None = a_rectification(
            rectified=(229.0, 228.5, 183.5, 124.0), raw=(229.0, 228.5, 183.5, 124.0)
        )
        self.closed = False
        self.dropped_frames = 0
        self.odom_state = "tracking"
        self.keyframe_count = 1

    @property
    def last_odom_frame(self) -> int:
        return max((f for f in self._odometry if f <= self._arrived_through), default=0)

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        # Odometry for frame f arrives once frame f + lag has been sent
        self._arrived_through = frame.frame_id - self._odometry_lag
        return FrameResult(frame.frame_id, frame.t_ns, self._trajectory[-1], ())

    def frame_odometry(self, frame_id: int) -> OdomUpdate | None:
        return self._odometry.get(frame_id) if frame_id <= self._arrived_through else None

    def poll_updates(self) -> list[MapUpdate]:
        return []

    def map_cloud(self) -> MapCloud:
        return self.cloud

    def map_snapshot(self) -> tuple[Vec3, ...]:
        return tuple(Vec3(*map(float, row)) for row in self.cloud.points.tolist())

    def trajectory(self) -> list[Pose]:
        return self._trajectory

    def flush(self) -> list[FrameResult]:
        self._arrived_through = max(self._odometry, default=0)
        last = self._trajectory[-1]
        return [FrameResult(1, 100, last, self.map_snapshot())]

    def close(self) -> None:
        self.closed = True


class MatcherThatMustNotRun(StereoReconstructor):
    """The numpy matcher, failing loudly if the live overlay calls it."""

    def reconstruct(self, left: FrameImage, right: FrameImage, rig: StereoRig) -> tuple[Vec3, ...]:
        raise AssertionError("the live overlay ran the numpy stereo matcher")


class BlockingDetector:
    """Detection source that blocks every call until `release` is set."""

    def __init__(self) -> None:
        self.release = threading.Event()

    def detect_tracked(self, frame_id: int, rgb: NDArray[np.uint8]) -> tuple[TrackedDetection, ...]:
        assert self.release.wait(timeout=10), "detector was never released"
        return (TrackedDetection("car", 0.9, (1.0, 2.0, 30.0, 40.0), 7, frame_id),)


def floor_pixel(png_b64: object, u: float, v: float) -> tuple[int, int, int, int]:
    """The RGBA of a map-image pixel."""
    assert isinstance(png_b64, str)
    with Image.open(io.BytesIO(base64.b64decode(png_b64))) as image:
        pixel = image.convert("RGBA").getpixel((int(u), int(v)))
    assert isinstance(pixel, tuple) and len(pixel) == 4
    r, g, b, a = (int(channel) for channel in pixel)
    return r, g, b, a


def an_extent(raw: object) -> FloorExtent:
    """The extent a map event sends as [min_x, max_x, min_z, max_z]."""
    assert isinstance(raw, list) and len(raw) == 4
    min_x, max_x, min_z, max_z = (float(value) for value in raw)
    return FloorExtent(min_x, max_x, min_z, max_z)


def a_rectification(
    rotation: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    rectified: tuple[float, float, float, float] = (200.0, 200.0, 100.0, 80.0),
    raw: tuple[float, float, float, float] = (200.0, 200.0, 100.0, 80.0),
    distortion: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
) -> Rectification:
    return Rectification(rotation, rectified, raw, distortion)


def _odom_with(
    *keypoints: Keypoint, pose: Pose | None = None, map_pose: Pose | None = None
) -> OdomUpdate:
    return OdomUpdate(0, 0, pose or Pose(Vec3(0.0, 0.0, 0.0)), False, 1.0, keypoints, map_pose)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (752, 480), 90).save(buffer, format="PNG")
    return buffer.getvalue()


def _tiny_zip(path: Path) -> DatasetSpec:
    png = _png_bytes()
    with zipfile.ZipFile(path, "w") as archive:
        for t_ns in (100, 200):
            archive.writestr(f"mav0/cam0/data/{t_ns}.png", png)
            archive.writestr(f"mav0/cam1/data/{t_ns}.png", png)
        archive.writestr("mav0/cam0/sensor.yaml", CAM0_YAML)
        archive.writestr("mav0/cam1/sensor.yaml", CAM1_YAML)
        archive.writestr("mav0/imu0/sensor.yaml", "sensor_type: imu\n")
        archive.writestr("mav0/imu0/data.csv", "t,wx,wy,wz,ax,ay,az\n")
    data = path.read_bytes()
    return DatasetSpec(
        dataset_id="tiny-test",
        title="Tiny Test",
        description="two pairs",
        zip_url="https://example.invalid/tiny.zip",
        zip_size_bytes=len(data),
        zip_sha256=hashlib.sha256(data).hexdigest(),
        official_url="https://example.invalid/",
    )


def test_the_registry_has_the_euroc_dataset() -> None:
    spec = DATASETS["euroc-v1-01-easy"]
    assert spec.dataset_format == "euroc"
    assert spec.zip_sha256.startswith("a920fe5b")
    assert spec.zip_size_bytes > 1_000_000_000


def test_ensure_dataset_downloads_once_then_hits_the_cache(tmp_path: Path) -> None:
    zip_path = tmp_path / "tiny.zip"
    spec = _tiny_zip(zip_path)
    downloads: list[str] = []

    def fetch(url: str, target: Path) -> None:
        downloads.append(url)
        target.write_bytes(zip_path.read_bytes())

    cache = tmp_path / "cache"
    prepared = ensure_dataset(spec, cache, log=lambda _: None, fetch=fetch)
    again = ensure_dataset(spec, cache, log=lambda _: None, fetch=fetch)

    assert downloads == [spec.zip_url]  # second run was a cache hit
    assert prepared.timestamps_ns == (100, 200)
    assert again.root == prepared.root
    calibration = load_calibration(prepared)
    assert calibration.width == 752
    assert abs(calibration.baseline_m - 0.11) < 1e-9


def test_scaled_sensor_yaml_halves_intrinsics_and_resolution() -> None:
    scaled = scaled_sensor_yaml(CAM0_YAML, 376, 240)
    assert "resolution: [376, 240]" in scaled
    assert "intrinsics: [229.0, 228.5, 183.5, 124.0]" in scaled


def test_project_overlay_filters_and_samples() -> None:
    from surmap.demo.datasets import DemoCalibration

    calibration = DemoCalibration(100.0, 100.0, 50.0, 50.0, 0.1, 100, 100)
    points = (
        Vec3(0.0, 0.0, 1.0),  # centre
        Vec3(0.0, 0.0, -1.0),  # behind
        Vec3(10.0, 0.0, 1.0),  # off-frame
    )
    overlay = project_overlay(points, calibration)
    assert overlay == [{"x": 50.0, "y": 50.0, "d": 1.0}]


def _write_zip_to(_url: str, target: Path, source: Path) -> None:
    target.write_bytes(source.read_bytes())


def _prepared_tiny(tmp_path: Path) -> PreparedDataset:
    zip_path = tmp_path / "tiny.zip"
    spec = _tiny_zip(zip_path)
    return ensure_dataset(
        spec,
        tmp_path / "cache",
        log=lambda _: None,
        fetch=lambda url, target: _write_zip_to(url, target, zip_path),
    )


def test_demo_server_serves_page_health_and_stream_then_closes(tmp_path: Path) -> None:
    prepared = _prepared_tiny(tmp_path)
    server = make_demo_server(prepared, host="127.0.0.1", port=0, with_rtabmap=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=5) as response:
            assert json.loads(response.read()) == {"status": "ok"}
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
            assert b"SurMap Test Console" in response.read()
        with urllib.request.urlopen(f"http://{host}:{port}/stream", timeout=10) as response:
            body = response.read().decode()
        assert body.count("event: frame") == 2
        assert '"point_count"' in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_player_paces_frames_and_closes_its_backend(tmp_path: Path) -> None:
    prepared = _prepared_tiny(tmp_path)
    player = DemoPlayer(prepared, fps=50.0, with_rtabmap=False)
    events = list(player.events())
    assert [event.kind for event in events] == ["frame", "frame"]
    assert all(event.jpeg for event in events)
    with pytest.raises(ValueError, match="fps"):
        DemoPlayer(prepared, fps=0, with_rtabmap=False)


def test_the_rate_meter_reports_a_cumulative_counter_per_second() -> None:
    from surmap.demo.server import _RateMeter

    # Given a meter watching RTAB-Map's odometry counter
    meter = _RateMeter(window_s=10.0)

    # When the counter advances 100 frames over 4 seconds
    assert meter.sample(0.0, 0) == 0.0
    rate = meter.sample(4.0, 100)

    # Then the rate is the advance per second, and a stalled counter
    # (no new odometry inside the window) decays back to zero
    assert rate == 25.0
    assert meter.sample(20.0, 100) == 0.0


def test_live_map_events_carry_the_rtab_frame_rate(tmp_path: Path) -> None:
    # Given a live backend whose odometry lands for every frame
    odometry = {
        frame_id: OdomUpdate(frame_id, frame_id * 10, Pose(Vec3(0.0, 0.0, 0.0)), False, 1.0)
        for frame_id in range(1, 65)
    }
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=lambda: FakeLiveBackend(odometry=odometry),
    )

    # When the player runs
    events = list(player.events())

    # Then every map event names the RTAB-Map processing rate
    map_events = [event for event in events if event.kind == "map"]
    assert map_events
    assert all(isinstance(event.data["rtab_fps"], float) for event in map_events)
    assert all(float(str(event.data["rtab_fps"])) >= 0.0 for event in map_events)


def test_player_emits_live_map_events_before_final_and_closes_backend(tmp_path: Path) -> None:
    # Given a live backend
    fake = FakeLiveBackend()
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=lambda: fake,
    )

    # When the player runs to the end
    events = list(player.events())

    # Then map events arrive during playback (before final), final
    # still arrives, and the backend is closed
    kinds = [event.kind for event in events]
    assert "map" in kinds
    assert kinds.index("map") < kinds.index("final")
    assert kinds[-1] == "final"
    assert events[kinds.index("map")].data["odom_state"] == "tracking"
    assert fake.closed


def test_live_map_plots_the_floor_plane_in_point_colour(tmp_path: Path) -> None:
    # Given a map point 5 m ahead, 2 m below the camera's start, and a
    # camera that moved 2 m forward and 1 m up
    fake = FakeLiveBackend(
        cloud=[((1.0, 2.0, 5.0), (10, 20, 30))],
        trajectory=[Pose(Vec3(0.5, -1.0, 2.0))],
    )
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=lambda: fake,
    )

    # When the first map event is emitted
    map_event = next(event for event in player.events() if event.kind == "map")

    # Then the trajectory is on the floor plane (x, z) — the optical
    # frame's y is height — and the map image shows the point there in its
    # own grey (r=10 here), within an extent covering both
    assert map_event.data["trajectory_xy"] == [[0.5, 2.0]]
    extent = an_extent(map_event.data["extent"])
    assert extent.min_x <= 0.5 and extent.max_x >= 1.0 and extent.max_z >= 5.0
    u, v = extent.to_pixels(1.0, 5.0)
    assert floor_pixel(map_event.data["floor_png"], u, v)[0] == 10


def test_live_frame_shows_its_own_tracked_keypoints_once_its_odometry_arrived(
    tmp_path: Path,
) -> None:
    # Given odometry that arrives one frame late, tracking word 5 on
    # each frame at a slightly different pixel and depth
    fake = FakeLiveBackend(
        odometry={
            1: _odom_with(Keypoint(5, 183.5, 124.0, 0.5)),
            2: _odom_with(Keypoint(5, 190.0, 124.0, 0.6)),
        },
        odometry_lag=1,
    )
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=lambda: fake,
        stereo=MatcherThatMustNotRun(),
    )

    # When playback runs to the end
    frames = [event for event in player.events() if event.kind == "frame"]

    # Then each frame, in order, carries its own frame's keypoint
    assert [frame.data["frame_id"] for frame in frames] == [1, 2]
    assert frames[0].data["detections"] == [
        {"x": 183.5, "y": 124.0, "d": 0.5, "c": depth_colour(0.5)}
    ]
    assert frames[1].data["detections"] == [
        {"x": 190.0, "y": 124.0, "d": 0.6, "c": depth_colour(0.6)}
    ]


def test_a_frame_whose_pair_was_dropped_is_shown_without_keypoints(tmp_path: Path) -> None:
    # Given RTAB-Map dropped frame 1's pair and tracked frame 2
    fake = FakeLiveBackend(odometry={2: _odom_with(Keypoint(5, 183.5, 124.0, 2.0))})
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=lambda: fake,
    )

    # When playback runs to the end
    frames = [event for event in player.events() if event.kind == "frame"]

    # Then frame 1 is still shown, with no keypoints, and frame 2 has its own
    assert [frame.data["frame_id"] for frame in frames] == [1, 2]
    assert frames[0].data["detections"] == []
    assert frames[1].data["point_count"] == 1


def test_rectified_pixels_map_back_through_the_lens_distortion() -> None:
    # Given a rectification with barrel distortion k1 = -0.2 and no rotation
    rectification = a_rectification(distortion=(-0.2, 0.0, 0.0, 0.0))

    # When a rectified pixel half a focal length right of centre is mapped
    raw = rectified_to_raw(np.array([[200.0, 80.0]]), rectification)

    # Then it lands where the distortion pulls it in: x 0.5 -> 0.475
    assert raw.tolist() == [[195.0, 80.0]]


def test_rectified_pixels_map_back_through_the_rectification_rotation() -> None:
    # Given a rectification that rotated the raw camera 90 degrees about z
    rectification = a_rectification(rotation=(0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0))

    # When a rectified pixel half a focal length right of centre is mapped
    raw = rectified_to_raw(np.array([[200.0, 80.0]]), rectification)

    # Then the raw ray is rotated back: half a focal length up
    assert raw.tolist() == [[100.0, -20.0]]


def test_depth_colours_run_red_near_through_orange_to_teal_far() -> None:
    # Given / When / Then the ramp's stops, clamped beyond them
    assert depth_colour(0.2) == "#ff5a3c"
    assert depth_colour(1.0) == "#ff5a3c"
    assert depth_colour(3.0) == "#ffb03a"
    assert depth_colour(6.0) == "#2fd4c4"
    assert depth_colour(9.0) == "#2fd4c4"


def test_a_slow_detector_does_not_stall_playback(tmp_path: Path) -> None:
    # Given a detector that blocks until the test releases it
    detector = BlockingDetector()
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=50.0,
        with_rtabmap=False,
        detection_source=detector,
    )

    # When playback runs, releasing the detector only after both frames
    kinds: list[str] = []
    detected_frames: list[object] = []
    for event in player.events():
        kinds.append(event.kind)
        if event.kind == "detections":
            detected_frames.append(event.data["frame_id"])
        if kinds.count("frame") == 2:
            detector.release.set()

    # Then both frames played before any detection, and every frame's
    # detections still arrived, in frame order
    assert kinds == ["frame", "frame", "detections", "detections"]
    assert detected_frames == [1, 2]


def test_player_emits_detections_as_a_separate_frame_keyed_event(tmp_path: Path) -> None:
    from typing import Any

    class StubSource:
        def detect_tracked(self, frame_id: int, rgb: Any) -> tuple[TrackedDetection, ...]:
            return (TrackedDetection("car", 0.9, (1.0, 2.0, 30.0, 40.0), 7, frame_id),)

    prepared = _prepared_tiny(tmp_path)
    player = DemoPlayer(
        prepared,
        fps=50.0,
        with_rtabmap=False,
        detection_source=StubSource(),
    )
    events = list(player.events())
    # Detections are their own events carrying frame_id — never a
    # field riding on the frame events — and each follows its frame
    kinds = [event.kind for event in events]
    assert kinds.count("frame") == 2 and kinds.count("detections") == 2
    assert kinds[0] == "frame"
    detections = events[kinds.index("detections")]
    assert detections.data["frame_id"] == 1
    objects = detections.data["objects"]
    assert isinstance(objects, list)
    assert objects[0]["track_id"] == 7
    assert "objects" not in events[0].data


def test_live_frame_carries_its_camera_on_the_floor_plan(tmp_path: Path) -> None:
    # Given frame 1's odometry: the camera 1 m right, 2 m ahead of where it
    # started, half a metre up, and turned 90 degrees to face +x
    turned_right = Pose(
        Vec3(1.0, -0.5, 2.0), (0.0, math.sin(math.pi / 4), 0.0, math.cos(math.pi / 4))
    )
    fake = FakeLiveBackend(odometry={1: _odom_with(pose=turned_right)})
    player = DemoPlayer(_prepared_tiny(tmp_path), fps=1000.0, backend_factory=lambda: fake)

    # When frame 1 is shown
    frame = next(event for event in player.events() if event.kind == "frame")

    # Then it carries the camera's floor-plan position, heading and the
    # display's horizontal field of view (2·atan(188 / 229))
    assert frame.data["camera"] == {"x": 1.0, "z": 2.0, "dx": 1.0, "dz": 0.0, "fov_deg": 78.8}


def test_a_frame_without_odometry_carries_no_camera(tmp_path: Path) -> None:
    # Given RTAB-Map dropped frame 1's pair and tracked frame 2
    fake = FakeLiveBackend(odometry={2: _odom_with()})
    player = DemoPlayer(_prepared_tiny(tmp_path), fps=1000.0, backend_factory=lambda: fake)

    # When playback runs
    frames = [event for event in player.events() if event.kind == "frame"]

    # Then frame 1 has no camera to draw, and frame 2 has one
    assert frames[0].data["camera"] is None
    assert frames[1].data["camera"] is not None


def test_without_rtabmap_frames_carry_no_camera(tmp_path: Path) -> None:
    # Given / When playback without SLAM
    player = DemoPlayer(_prepared_tiny(tmp_path), fps=1000.0, with_rtabmap=False)
    frame = next(event for event in player.events() if event.kind == "frame")

    # Then there is no camera pose to show
    assert frame.data["camera"] is None


def test_sam_video_events_arrive_for_each_frame_in_order(tmp_path: Path) -> None:
    # Given a SAM video source that segments every frame of the stream
    from surmap.survey.sam import InMemoryVideoSamDetector, SamDetection

    sam = InMemoryVideoSamDetector(
        (SamDetection("car", 0.9, (1.0, 2.0, 30.0, 40.0), ((1.0, 2.0), (30.0, 40.0))),)
    )
    player = DemoPlayer(_prepared_tiny(tmp_path), fps=1000.0, with_rtabmap=False, sam_source=sam)

    # When playback runs to the end
    events = list(player.events())

    # Then each frame has its own SAM event, in frame order, after the
    # first frame (SAM runs off the frame loop, like the Coral stream)
    kinds = [event.kind for event in events]
    assert kinds.count("frame") == 2 and kinds.count("sam") == 2
    assert kinds.index("sam") > kinds.index("frame")
    sam_events = [event for event in events if event.kind == "sam"]
    assert [event.data["frame_id"] for event in sam_events] == [1, 2]
    objects = sam_events[0].data["objects"]
    assert isinstance(objects, list)
    assert objects[0]["label"] == "car"
    assert objects[0]["track_id"] == 1
    assert objects[0]["mask_polygon"] == [[1.0, 2.0], [30.0, 40.0]]
    assert [frame.frame_id for frame in sam.frames] == [1, 2]


def test_the_page_shows_sam_masks_when_sam_is_enabled(tmp_path: Path) -> None:
    # Given a demo server with a SAM video source
    from surmap.survey.sam import InMemoryVideoSamDetector, SamDetection

    sam = InMemoryVideoSamDetector(
        (SamDetection("car", 0.9, (1.0, 2.0, 30.0, 40.0), ((1.0, 2.0), (30.0, 40.0))),)
    )
    server = make_demo_server(
        _prepared_tiny(tmp_path), host="127.0.0.1", port=0, with_rtabmap=False, sam_source=sam
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = str(server.server_address[0]), int(server.server_address[1])
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
            page = response.read().decode()
        with urllib.request.urlopen(f"http://{host}:{port}/stream", timeout=10) as response:
            body = response.read().decode()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    # Then the page has a separate SAM pane and the stream sends
    # SAM results per frame, each with its frame image
    assert "addEventListener('sam'" in page
    assert "SAM (video)" in page
    assert 'id="sam-view"' in page
    assert body.count("event: sam") == 2
    assert '"track_id": 1' in body


def test_sam_streamer_events_arrive_for_each_frame_in_order(tmp_path: Path) -> None:
    # Given a whole-video SAM streamer (SAM 3.1's native session mode)
    from surmap.survey.sam import InMemoryVideoSamStreamer, SamDetection

    streamer = InMemoryVideoSamStreamer(
        (SamDetection("car", 0.9, (1.0, 2.0, 30.0, 40.0), ((1.0, 2.0), (30.0, 40.0))),)
    )
    player = DemoPlayer(
        _prepared_tiny(tmp_path), fps=1000.0, with_rtabmap=False, sam_streamer=streamer
    )

    # When playback runs to the end
    events = list(player.events())

    # Then each played frame has its own SAM event, in frame order
    sam_events = [event for event in events if event.kind == "sam"]
    assert [event.data["frame_id"] for event in sam_events] == [1, 2]
    assert len(streamer.videos) == 1 and len(streamer.videos[0]) == 2


def test_frames_play_at_their_own_rate_without_waiting_for_sam(tmp_path: Path) -> None:
    # Given a SAM streamer that holds its results until released
    # (SAM propagates much slower than playback, on its own pane)
    from collections.abc import Iterator, Sequence

    from surmap.survey.sam import SamDetection

    class BlockingStreamer:
        def __init__(self) -> None:
            self.release = threading.Event()

        def stream(
            self, frame_paths: Sequence[Path], prompt: str | None = None
        ) -> Iterator[tuple[int, tuple[SamDetection, ...]]]:
            assert self.release.wait(timeout=15), "streamer was never released"
            for index in range(len(frame_paths)):
                yield index, (SamDetection("car", 0.9, (1.0, 2.0, 30.0, 40.0), ((1.0, 2.0),)),)

        def close(self) -> None:
            pass

    streamer = BlockingStreamer()
    player = DemoPlayer(
        _prepared_tiny(tmp_path), fps=1000.0, with_rtabmap=False, sam_streamer=streamer
    )

    # When playback runs, the main frames are shown without waiting for SAM
    events: list[DemoEvent] = []
    collector = threading.Thread(target=lambda: events.extend(player.events()), daemon=True)
    collector.start()
    collector.join(timeout=2.0)
    assert [event.kind for event in events] == ["frame", "frame"]

    # And once SAM delivers, its events arrive on their own cadence,
    # each carrying the frame image for the separate SAM pane
    streamer.release.set()
    collector.join(timeout=15)
    sam_events = [event for event in events if event.kind == "sam"]
    assert [event.data["frame_id"] for event in sam_events] == [1, 2]
    assert all(event.jpeg for event in sam_events)


def test_the_demo_cli_names_the_sam_gpu_device_argument() -> None:
    # Given / When the launcher is asked for its help
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/demo.py", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    # Then the optional SAM device argument is listed, defaulting to
    # the real SAM 3.1 checkpoint, with --sam-model as an override
    assert result.returncode == 0
    assert "--sam-device" in result.stdout
    assert "--sam-model" in result.stdout
    assert "facebook/sam3.1" in result.stdout

    # And a model without a device is a clear command-line error, not a silent no-op
    missing = subprocess.run(
        [sys.executable, "scripts/demo.py", "--sam-model", "facebook/sam3.1"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert missing.returncode == 2
    assert "--sam-device" in missing.stderr


def test_the_cloud_view_is_the_floor_plan_renderer_from_a_ptz_pose() -> None:
    # Given a coloured surface cloud
    from surmap.demo.server import CloudPose, render_cloud_view

    rng = np.random.default_rng(3)
    points = rng.uniform(-5.0, 5.0, size=(2_000, 3)).astype(np.float32)
    colors = rng.integers(0, 255, size=(2_000, 3), dtype=np.uint8)
    bounds = (points.min(axis=0), points.max(axis=0))

    # When the same cloud is rendered from the same pose twice, and
    # once from a different azimuth
    first = render_cloud_view(points, colors, CloudPose(), bounds)
    again = render_cloud_view(points, colors, CloudPose(), bounds)
    turned = render_cloud_view(points, colors, CloudPose(azimuth=1.2), bounds)

    # Then rendering is deterministic (no sampling churn), the pose
    # changes the picture, and points actually land in it
    assert first == again
    assert turned != first
    import base64
    import io

    from PIL import Image

    image = Image.open(io.BytesIO(base64.b64decode(first)))
    assert image.size == (880, 440)
    pixels = np.array(image.convert("RGB")).reshape(-1, 3)
    assert int(np.count_nonzero(np.any(pixels != (10, 12, 14), axis=1))) > 500


def test_map_events_carry_the_server_rendered_cloud_view(tmp_path: Path) -> None:
    # Given a live backend with a coloured cloud
    fake = FakeLiveBackend(odometry={1: _odom_with(), 2: _odom_with()})
    player = DemoPlayer(_prepared_tiny(tmp_path), fps=1000.0, backend_factory=lambda: fake)

    # When playback runs
    map_event = next(event for event in player.events() if event.kind == "map")

    # Then the map event carries the cloud rendered server-side from
    # the shared PTZ pose, like the floor plan image it also carries
    assert isinstance(map_event.data["cloud_png"], str)
    assert len(str(map_event.data["cloud_png"])) > 100


def test_the_sampled_cloud_is_dense_and_stable_as_the_map_grows() -> None:
    # Given a map cloud well above the draw cap, on surfaces (as
    # RTAB-Map clouds lie on walls/floors, not through volumes)
    rng = np.random.default_rng(7)

    def surface(count: int) -> NDArray[np.float32]:
        directions = rng.normal(size=(count, 3))
        directions /= np.linalg.norm(directions, axis=1, keepdims=True)
        return (directions * 8.0).astype(np.float32)

    base = surface(30_000)
    colors = np.full((30_000, 3), 128, dtype=np.uint8)
    grown = np.concatenate([base, surface(1_000)])
    grown_colors = np.full((31_000, 3), 128, dtype=np.uint8)

    # When the cloud is sampled, then sampled again after it grows
    first, _ = cloud_points(MapCloud(base, colors), max_points=1_000)
    second, _ = cloud_points(MapCloud(grown, grown_colors), max_points=1_000)

    # Then the cap is fully used in both samples (dense, not voxel-
    # starved), and at least 90% of the drawn points survive the
    # growth: the 3D pixels must not jump between map updates
    assert len(first) == len(second) == 1_000
    kept = {tuple(point) for point in first} & {tuple(point) for point in second}
    assert len(kept) >= 900
