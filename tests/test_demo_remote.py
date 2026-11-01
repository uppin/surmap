"""Fluent tests for the demo's remote CM5/Station wire clients.

The demo page can run against the deployed servers instead of its
in-process pipelines: `RemoteCm5Backend` (survey points over
`StreamSurvey`), `RemoteDetectionSource` (Coral over
`StreamDetections`), and `RemoteSamDetector` (SAM over
`StreamAnalysis`), with `fetch_capabilities` deciding which panes the
page renders. Servers here are the real service descriptions on a
local socket; no hardware, no live models.
"""

import asyncio
import threading
import urllib.request
from pathlib import Path

import numpy as np
import pytest

from surmap.demo.datasets import DATASETS, DemoCalibration, PreparedDataset, load_calibration
from surmap.demo.remote import (
    RemoteCm5Backend,
    RemoteDetectionSource,
    RemoteSamDetector,
    fetch_capabilities,
)
from surmap.demo.server import make_demo_server
from surmap.detection.tracker import TrackedDetection
from surmap.types import StereoFramePair
from tests.test_demo import _prepared_tiny
from tests.test_survey_server_e2e import running_server

ROOT = Path(__file__).resolve().parent.parent
EUROC = ROOT / "tests" / "fixtures" / "euroc_v101_rtabmap"


def _euroc_pair(index: int, t_ns: int) -> StereoFramePair:
    return StereoFramePair(
        frame_id=index + 1,
        t_ns=t_ns,
        left_ref=f"frame-{index + 1}-left",
        right_ref=f"frame-{index + 1}-right",
        calibration_id="euroc-remote",
        left_data=(EUROC / "mav0" / "cam0" / "data" / f"{t_ns}.jpg").read_bytes(),
        right_data=(EUROC / "mav0" / "cam1" / "data" / f"{t_ns}.jpg").read_bytes(),
    )


def _require_euroc() -> None:
    if not (EUROC / "manifest.json").is_file():
        pytest.skip("run `uv run python scripts/fetch_rtabmap_fixture.py` first")


def test_capabilities_of_an_unreachable_host_are_none() -> None:
    # Given a host address where nothing listens
    # When its capabilities are fetched
    # Then there is nothing to report (the demo hides that host's panes)
    assert fetch_capabilities("127.0.0.1:1", "Cm5SurveyService") is None


async def test_capabilities_of_a_live_cm5_host_describe_its_build() -> None:
    from surmap.survey.cm5_main import build_description

    # Given a real CM5 server on a local socket (bare build)
    async with running_server(build_description()) as address:
        # When its capabilities are fetched over the wire
        capabilities = await asyncio.to_thread(fetch_capabilities, address, "Cm5SurveyService")

    # Then they name the service and what it was built without
    assert capabilities is not None
    assert capabilities.service == "cm5"
    assert capabilities.detections is False
    assert capabilities.slam == "inmemory"


async def test_the_remote_cm5_backend_builds_its_cloud_from_survey_points() -> None:
    _require_euroc()
    from surmap.survey.cm5_main import build_description

    # Given a real CM5 server (in-memory pose + stereo scene points)
    calibration = load_calibration(PreparedDataset(DATASETS["euroc-v1-01-easy"], EUROC, ())).scaled(
        376, 240
    )
    async with running_server(build_description()) as address:
        backend = RemoteCm5Backend(address, calibration, (376, 240))
        try:
            # When the played pairs are streamed to it and flushed
            import json

            timestamps = json.loads((EUROC / "manifest.json").read_text())["frame_timestamps_ns"]

            def play() -> None:
                for index, t_ns in enumerate(timestamps[:6]):
                    backend.process_frame(_euroc_pair(index, int(t_ns)))
                backend.flush()

            await asyncio.to_thread(play)

            # Then the demo's cloud is the server's scene points
            cloud = backend.map_cloud()
            assert len(cloud.points) > 0
            assert backend.keyframe_count > 0
        finally:
            backend.close()


async def test_the_remote_detection_source_returns_the_servers_tracks() -> None:
    from surmap.survey.cm5_main import build_description

    # Given a CM5 server whose detector reports one tracked car
    class StubSource:
        def detect_tracked(self, frame_id: int, rgb: np.ndarray) -> tuple[TrackedDetection, ...]:
            return (TrackedDetection("car", 0.9, (1.0, 2.0, 30.0, 40.0), 7, frame_id),)

    async with running_server(build_description(detections=StubSource())) as address:
        source = RemoteDetectionSource(address)

        # When a frame is analyzed through the wire client
        tracked = await asyncio.to_thread(
            source.detect_tracked, 3, np.zeros((240, 376, 3), dtype=np.uint8)
        )

    # Then the server's detection and track id come back unchanged
    assert [(d.label, d.track_id) for d in tracked] == [("car", 7)]


async def test_the_remote_sam_detector_tracks_the_stations_detections() -> None:
    from surmap.survey.sam import InMemorySamDetector, RawFrame, SamDetection
    from surmap.survey.station_main import build_description as station_description

    # Given a station server with a configured in-memory detection
    detection = SamDetection("car", 0.9, (10.0, 10.0, 60.0, 60.0), ((10.0, 10.0), (60.0, 60.0)))
    detector = InMemorySamDetector((detection,))
    async with running_server(station_description(detector=detector)) as address:
        source = RemoteSamDetector(address, "car")
        try:
            # When two frames are tracked through the wire client
            first = await asyncio.to_thread(
                source.track, RawFrame(1, 100, 0, 376, 240, "mjpeg", b"jpeg")
            )
            second = await asyncio.to_thread(
                source.track, RawFrame(2, 200, 0, 376, 240, "mjpeg", b"jpeg")
            )

            # Then detections carry persistent track ids, and the
            # station's execution is the one it reported
            assert [d.track_id for d in first] == [d.track_id for d in second] != [-1]
            assert source.provider == "InMemorySamDetector"
            assert source.device == "cpu"
        finally:
            source.close()


def _calibration() -> DemoCalibration:
    """A EuRoC-like calibration at display size, without the fixture.

    The stub-server tests only need plausible numbers on the wire;
    the real fixture under tests/fixtures is not in git.
    """
    return DemoCalibration(229.33, 228.65, 183.61, 124.19, 0.11007, 376, 240)


async def test_the_remote_backend_receives_odometry_and_live_points_before_flush() -> None:
    from surmap.slam.base import FrameResult
    from surmap.slam.stream_protocol import KeyframeUpdate, Keypoint, OdomUpdate, Rectification
    from surmap.survey.cm5_main import build_description
    from surmap.types import Pose, Vec3

    rect = Rectification(
        rotation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        rectified=(400.0, 400.0, 188.0, 120.0),
        raw=(400.0, 400.0, 188.0, 120.0),
        distortion=(0.0, 0.0, 0.0, 0.0),
    )

    # Given a CM5 server whose SLAM reports per-frame odometry (pose +
    # tracked keypoints) and a live map snapshot, like the streaming
    # RTAB-Map backend does
    class StubSlam:
        rectification = rect

        def __init__(self) -> None:
            self.mapped = False

        def process_frame(self, frame: StereoFramePair) -> FrameResult:
            self.mapped = True
            return FrameResult(frame.frame_id, frame.t_ns, None, ())

        def poll_updates(self) -> list[KeyframeUpdate]:
            if not self.mapped:
                return []
            self.mapped = False
            return [KeyframeUpdate(1, 1, 10, Pose(Vec3(0.0, 0.0, 0.0)), (Vec3(1.0, 2.0, 3.0),))]

        def frame_odometry(self, frame_id: int) -> OdomUpdate:
            pose = Pose(Vec3(1.0, 0.0, 0.0))
            return OdomUpdate(
                frame_id, frame_id * 10, pose, False, 1.0, (Keypoint(7, 10.0, 12.0, 2.5),), pose
            )

        def map_snapshot(self) -> tuple[Vec3, ...]:
            return ()

        def trajectory(self) -> list[Pose]:
            return []

        def close(self) -> None:
            pass

    calibration = _calibration()
    async with running_server(build_description(slam=StubSlam(), use_stereo=False)) as address:
        backend = RemoteCm5Backend(address, calibration, (376, 240))
        try:
            # When two pairs are played (with no flush yet)
            def play() -> None:
                for frame_id in (1, 2):
                    backend.process_frame(
                        StereoFramePair(frame_id, frame_id * 10, "l", "r", "cal", b"left", b"right")
                    )

            await asyncio.to_thread(play)

            # Then odometry, its keypoints and the live cloud arrive
            # during the stream, not only at flush
            deadline = asyncio.get_running_loop().time() + 15
            odom = backend.frame_odometry(1)
            while odom is None and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.05)
                odom = backend.frame_odometry(1)
            assert odom is not None
            assert [k.word_id for k in odom.keypoints] == [7]
            assert odom.pose is not None and odom.pose.position.x == 1.0
            assert backend.rectification == rect
            assert [tuple(p) for p in backend.map_cloud().points.tolist()] == [(1.0, 2.0, 3.0)]
            assert backend.trajectory()
        finally:
            await asyncio.to_thread(backend.close)


def _stub_slam(snapshot_x: float, odom_t_ns: int = 10, *, pre_mapped: bool = False) -> object:
    from surmap.slam.base import FrameResult
    from surmap.slam.stream_protocol import KeyframeUpdate, OdomUpdate
    from surmap.types import Pose, Vec3

    class StubSlam:
        rectification = None

        def __init__(self) -> None:
            self.mapped = pre_mapped

        def process_frame(self, frame: StereoFramePair) -> FrameResult:
            self.mapped = True
            return FrameResult(frame.frame_id, frame.t_ns, None, ())

        def poll_updates(self) -> list[KeyframeUpdate]:
            if not self.mapped:
                return []
            self.mapped = False
            return [
                KeyframeUpdate(
                    1, 1, odom_t_ns, Pose(Vec3(0.0, 0.0, 0.0)), (Vec3(snapshot_x, 2.0, 3.0),)
                )
            ]

        def frame_odometry(self, frame_id: int) -> OdomUpdate:
            return OdomUpdate(frame_id, odom_t_ns, Pose(Vec3(snapshot_x, 0.0, 0.0)), False, 1.0, ())

        def map_snapshot(self) -> tuple[Vec3, ...]:
            return (Vec3(snapshot_x, 2.0, 3.0),) if pre_mapped else ()

        def trajectory(self) -> list[Pose]:
            return []

        def close(self) -> None:
            pass

    return StubSlam()


async def test_each_survey_stream_gets_its_own_slam_built_from_the_stream_config() -> None:
    from surmap.survey.cm5_main import build_description

    # Given a CM5 server that builds a fresh SLAM backend per survey
    # stream from the stream's config (each stub maps one own point)
    built: list[object] = []
    configs: list[object] = []

    def factory(config: object) -> object:
        configs.append(config)
        slam = _stub_slam(float(len(built) + 1))
        built.append(slam)
        return slam

    calibration = _calibration()
    async with running_server(build_description(slam_factory=factory, use_stereo=False)) as address:  # type: ignore[arg-type]

        async def play_one() -> list[tuple[float, ...]]:
            backend = RemoteCm5Backend(
                address,
                calibration,
                (376, 240),
                cam_yamls=("CAM0-YAML", "CAM1-YAML"),
                max_depth_m=30.0,
            )
            try:
                await asyncio.to_thread(
                    backend.process_frame,
                    StereoFramePair(1, 10, "l", "r", "cal", b"left", b"right"),
                )
                await asyncio.to_thread(backend.flush)
                return [tuple(p) for p in backend.map_cloud().points.tolist()]
            finally:
                await asyncio.to_thread(backend.close)

        # When two runs play one pair each against the same server
        first = await play_one()
        second = await play_one()

    # Then each run's cloud is its own stream's map (no stale map from
    # the previous run), built from the config the client sent
    assert first == [(1.0, 2.0, 3.0)]
    assert second == [(2.0, 2.0, 3.0)]
    assert [c.cam0_yaml for c in configs] == ["CAM0-YAML", "CAM0-YAML"]  # type: ignore[attr-defined]
    assert [c.max_depth_m for c in configs] == [30.0, 30.0]  # type: ignore[attr-defined]


async def test_a_shared_slam_never_leaks_its_previous_map_or_odometry_into_a_stream() -> None:
    from surmap.survey.cm5_main import build_description

    # Given one shared SLAM backend that already holds a previous
    # run's map point and odometry for frame 1 (under another t_ns)
    calibration = _calibration()
    async with running_server(
        build_description(slam=_stub_slam(9.0, odom_t_ns=999, pre_mapped=True), use_stereo=False)  # type: ignore[arg-type]
    ) as address:
        backend = RemoteCm5Backend(address, calibration, (376, 240))
        try:
            # When a new stream plays frame 1 at t_ns 10
            await asyncio.to_thread(
                backend.process_frame,
                StereoFramePair(1, 10, "l", "r", "cal", b"left", b"right"),
            )
            await asyncio.to_thread(backend.flush)

            # Then neither the old map point nor the old odometry
            # shows up as this stream's output
            assert backend.map_cloud().points.tolist() == []
            assert backend.frame_odometry(1) is None
        finally:
            await asyncio.to_thread(backend.close)


async def test_a_keyframe_emits_at_most_the_stored_point_cap_placed_by_its_pose() -> None:
    from surmap.slam.base import FrameResult
    from surmap.slam.stream_protocol import KeyframeUpdate
    from surmap.survey.cm5_main import build_description
    from surmap.types import Pose, Vec3

    # Given a CM5 whose SLAM reports one keyframe carrying 2500 local
    # points under a pose 10 m ahead (the local backend stores at
    # most 1000 points per keyframe, and the wire matches it)
    class BigKeyframeSlam:
        rectification = None

        def __init__(self) -> None:
            self.mapped = False

        def process_frame(self, frame: StereoFramePair) -> FrameResult:
            self.mapped = True
            return FrameResult(frame.frame_id, frame.t_ns, None, ())

        def poll_updates(self) -> list[KeyframeUpdate]:
            if not self.mapped:
                return []
            self.mapped = False
            points = tuple(Vec3(float(i), 0.0, 0.0) for i in range(2500))
            return [KeyframeUpdate(1, 1, 10, Pose(Vec3(0.0, 0.0, 10.0)), points)]

        def trajectory(self) -> list[Pose]:
            return []

        def close(self) -> None:
            pass

    calibration = _calibration()
    async with running_server(
        build_description(slam=BigKeyframeSlam(), use_stereo=False)
    ) as address:
        backend = RemoteCm5Backend(address, calibration, (376, 240))
        try:
            # When one pair is played and flushed
            await asyncio.to_thread(
                backend.process_frame,
                StereoFramePair(1, 10, "l", "r", "cal", b"left", b"right"),
            )
            await asyncio.to_thread(backend.flush)

            # Then the cloud holds the capped keyframe, placed in the
            # map frame (z + 10 from the keyframe's pose)
            points = backend.map_cloud().points
            assert len(points) == 1000
            assert set(points[:, 2].tolist()) == {10.0}
        finally:
            await asyncio.to_thread(backend.close)


def _serve(server: object) -> tuple[str, threading.Thread]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)  # type: ignore[attr-defined]
    thread.start()
    host, port = server.server_address  # type: ignore[attr-defined]
    return f"http://{host}:{port}", thread


def test_the_page_hides_panes_for_hosts_that_do_not_answer(tmp_path: Path) -> None:
    # Given a demo launched at two hosts where nothing listens
    server = make_demo_server(
        _prepared_tiny(tmp_path),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        cm5_host="127.0.0.1:1",
        station_host="127.0.0.1:1",
    )
    base, thread = _serve(server)
    try:
        # When the page is rendered
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            page = response.read().decode()

        # Then neither host contributes panes (markup gone, CSS may stay)
        assert 'id="cloud-pane"' not in page
        assert 'id="sam-view"' not in page
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_the_local_page_keeps_its_cloud_pane_without_remote_hosts(tmp_path: Path) -> None:
    # Given a demo with no remote hosts (today's local behaviour)
    server = make_demo_server(
        _prepared_tiny(tmp_path), host="127.0.0.1", port=0, with_rtabmap=False
    )
    base, thread = _serve(server)
    try:
        # When the page is rendered
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            page = response.read().decode()

        # Then the RTAB-Map cloud pane is there, as before
        assert 'id="cloud-pane"' in page
    finally:
        server.shutdown()
        thread.join(timeout=5)
