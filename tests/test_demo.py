"""Demo tests: registry/cache logic, overlay projection, and a real
HTTP smoke of the demo server (started and closed in the test).
"""

import hashlib
import io
import json
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
    DemoCalibration,
    ensure_dataset,
    load_calibration,
    scaled_sensor_yaml,
)
from surmap.demo.server import (
    DemoPlayer,
    make_demo_server,
    project_map_overlay,
    project_overlay,
)
from surmap.detection.tracker import TrackedDetection
from surmap.slam.base import FrameResult
from surmap.slam.stream_protocol import MapUpdate
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
        latest: tuple[int, Pose] | None = None,
    ) -> None:
        entries = cloud if cloud is not None else [((1.0, 2.0, 0.0), (128, 128, 128))]
        self._cloud = MapCloud(
            np.array([xyz for xyz, _ in entries], dtype=np.float32).reshape(-1, 3),
            np.array([rgb for _, rgb in entries], dtype=np.uint8).reshape(-1, 3),
        )
        self._trajectory = trajectory if trajectory is not None else [Pose(Vec3(0.1, 0.0, 0.0))]
        self._latest = latest
        self.closed = False
        self.dropped_frames = 0
        self.odom_state = "tracking"
        self.last_odom_frame = 0
        self.keyframe_count = 1

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self.last_odom_frame = frame.frame_id
        return FrameResult(frame.frame_id, frame.t_ns, self._trajectory[-1], ())

    def poll_updates(self) -> list[MapUpdate]:
        return []

    def map_cloud(self) -> MapCloud:
        return self._cloud

    def map_snapshot(self) -> tuple[Vec3, ...]:
        return tuple(Vec3(*map(float, row)) for row in self._cloud.points.tolist())

    def latest_pose(self) -> tuple[int, Pose] | None:
        return self._latest

    def trajectory(self) -> list[Pose]:
        return self._trajectory

    def flush(self) -> list[FrameResult]:
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


def load_calibration_for_tests() -> DemoCalibration:
    """The tiny dataset's calibration at display size: fx 229, cx 183.5, cy 124."""
    return DemoCalibration(
        width=376, height=240, fx=229.0, fy=228.5, cx=183.5, cy=124.0, baseline_m=0.11
    )


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


def _prepared_tiny(tmp_path: Path) -> object:
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
    server = make_demo_server(prepared, host="127.0.0.1", port=0, with_rtabmap=False)  # type: ignore[arg-type]
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
    player = DemoPlayer(prepared, fps=50.0, with_rtabmap=False)  # type: ignore[arg-type]
    events = list(player.events())
    assert [event.kind for event in events] == ["frame", "frame"]
    assert all(event.jpeg for event in events)
    with pytest.raises(ValueError, match="fps"):
        DemoPlayer(prepared, fps=0, with_rtabmap=False)  # type: ignore[arg-type]


def test_player_emits_live_map_events_before_final_and_closes_backend(tmp_path: Path) -> None:
    # Given a live backend
    fake = FakeLiveBackend()
    player = DemoPlayer(
        _prepared_tiny(tmp_path),  # type: ignore[arg-type]
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
        _prepared_tiny(tmp_path),  # type: ignore[arg-type]
        fps=1000.0,
        backend_factory=lambda: fake,
    )

    # When the first map event is emitted
    map_event = next(event for event in player.events() if event.kind == "map")

    # Then points and trajectory are on the floor plane (x, z) — the
    # optical frame's y is height — and points keep their colour
    assert map_event.data["cloud_xy"] == [[1.0, 5.0, 10, 20, 30]]
    assert map_event.data["trajectory_xy"] == [[0.5, 2.0]]


def test_live_overlay_shows_rtabmap_points_at_their_camera_depth(tmp_path: Path) -> None:
    # Given a map point 4 m straight ahead of a camera that moved 1 m forward
    fake = FakeLiveBackend(
        cloud=[((0.0, 0.0, 4.0), (90, 90, 90))],
        latest=(1, Pose(Vec3(0.0, 0.0, 1.0))),
    )
    player = DemoPlayer(
        _prepared_tiny(tmp_path),  # type: ignore[arg-type]
        fps=1000.0,
        backend_factory=lambda: fake,
        stereo=MatcherThatMustNotRun(),
    )

    # When a frame is played
    frame = next(event for event in player.events() if event.kind == "frame")

    # Then the overlay is that RTAB-Map point, at the principal point, 3 m away
    assert frame.data["detections"] == [{"x": 183.5, "y": 124.0, "d": 3.0}]
    assert frame.data["point_count"] == 1


def test_overlay_projection_keeps_only_points_in_front_of_the_camera() -> None:
    # Given one point ahead of and one behind a camera turned 180° about y
    calibration = load_calibration_for_tests()
    turned = Pose(Vec3(0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0))
    points = np.array([[0.0, 0.0, -2.0], [0.0, 0.0, 2.0]], dtype=np.float32)

    # When they are projected
    overlay = project_map_overlay(points, turned, calibration)

    # Then only the point now in front is drawn, at its depth
    assert overlay == [{"x": 183.5, "y": 124.0, "d": 2.0}]


def test_a_slow_detector_does_not_stall_playback(tmp_path: Path) -> None:
    # Given a detector that blocks until the test releases it
    detector = BlockingDetector()
    player = DemoPlayer(
        _prepared_tiny(tmp_path),  # type: ignore[arg-type]
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
        prepared,  # type: ignore[arg-type]
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
