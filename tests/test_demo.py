"""Demo tests: registry/cache logic, overlay projection, and a real
HTTP smoke of the demo server (started and closed in the test).
"""

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
    DemoPlayer,
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
        self._cloud = MapCloud(
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
        return self._cloud

    def map_snapshot(self) -> tuple[Vec3, ...]:
        return tuple(Vec3(*map(float, row)) for row in self._cloud.points.tolist())

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


def a_rectification(
    rotation: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    rectified: tuple[float, float, float, float] = (200.0, 200.0, 100.0, 80.0),
    raw: tuple[float, float, float, float] = (200.0, 200.0, 100.0, 80.0),
    distortion: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
) -> Rectification:
    return Rectification(rotation, rectified, raw, distortion)


def _odom_with(*keypoints: Keypoint, pose: Pose | None = None) -> OdomUpdate:
    return OdomUpdate(0, 0, pose or Pose(Vec3(0.0, 0.0, 0.0)), False, 1.0, keypoints)


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
            assert b"SurMap demo" in response.read()
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

    # Then points and trajectory are on the floor plane (x, z) — the
    # optical frame's y is height — and points keep their colour
    assert map_event.data["cloud_xy"] == [[1.0, 5.0, 10, 20, 30]]
    assert map_event.data["trajectory_xy"] == [[0.5, 2.0]]


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
