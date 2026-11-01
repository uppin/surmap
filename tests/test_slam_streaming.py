"""Streaming backend tests with a fake process (no Docker)."""

import io
import json
import queue
import struct
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from surmap.slam.sidecar import SidecarError
from surmap.slam.stream_protocol import PROTOCOL_VERSION, Keypoint
from surmap.slam.streaming import (
    StreamingRtabmapBackend,
    _PopenProcess,
    keep_confident_camera_points,
    stream_build_argv,
)
from surmap.types import Pose, StereoFramePair, Vec3

CAM_YAML = "sensor_type: camera\nresolution: [376, 240]\n"


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (8, 6), 128).save(buffer, format="PNG")
    return buffer.getvalue()


def _frame(frame_id: int) -> StereoFramePair:
    return StereoFramePair(frame_id, frame_id * 1_000_000_000, "l", "r", "cal", _png(), _png())


class FakeProcess:
    """Scripted process: test pushes stdout lines; stdin is recorded."""

    def __init__(self, argv: list[str], ready: dict[str, object] | None = None) -> None:
        self.argv = argv
        self.written = bytearray()
        self.stdin_closed = threading.Event()
        self.terminated = False
        self._lines: queue.Queue[bytes] = queue.Queue()
        announced = {"type": "ready", "version": PROTOCOL_VERSION, **(ready or {})}
        self._lines.put((json.dumps(announced) + "\n").encode())

    def write(self, data: bytes) -> None:
        self.written.extend(data)

    def close_stdin(self) -> None:
        self.stdin_closed.set()
        self._lines.put(b'{"type":"graph","poses":[],"final":true}\n')
        self._lines.put(b"")

    def readline(self) -> bytes:
        return self._lines.get()

    def emit(self, obj: dict[str, object]) -> None:
        self._lines.put((json.dumps(obj) + "\n").encode())

    def terminate(self) -> None:
        self.terminated = True
        self._lines.put(b"")

    def wait(self, timeout: float | None = None) -> int:
        return 0


def _backend(
    fake_holder: list[FakeProcess],
    *,
    queue_size: int = 4,
    runner: Callable[[list[str]], None] | None = None,
    ready: dict[str, object] | None = None,
) -> StreamingRtabmapBackend:
    def factory(argv: list[str]) -> FakeProcess:
        proc = FakeProcess(argv, ready)
        fake_holder.append(proc)
        return proc

    if runner is None:
        return StreamingRtabmapBackend(
            cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, process_factory=factory, queue_size=queue_size
        )
    return StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML,
        cam1_yaml=CAM_YAML,
        process_factory=factory,
        queue_size=queue_size,
        runner=runner,
    )


class _BlockingProcess(FakeProcess):
    """Pair writes stall forever, as a slow RTAB-Map would."""

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self._writes = 0

    def write(self, data: bytes) -> None:
        self._writes += 1
        if self._writes > 1:  # hello goes through; pairs stall
            threading.Event().wait(timeout=5)


def test_process_frame_never_blocks_when_process_stalled() -> None:
    holder: list[FakeProcess] = []

    def factory(argv: list[str]) -> FakeProcess:
        proc = _BlockingProcess(argv)
        holder.append(proc)
        return proc

    backend = StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, process_factory=factory, queue_size=4
    )
    try:
        start = time.monotonic()
        for frame_id in range(1, 8):
            result = backend.process_frame(_frame(frame_id))
            assert result.pose is None  # nothing read back yet for it
        assert time.monotonic() - start < 2.0
        # 7 in: 1 stalled in the writer, 4 queued, the rest dropped oldest
        assert backend.dropped_frames >= 2
    finally:
        backend.close()


def test_native_backend_launches_the_binary_directly_without_docker(tmp_path: Path) -> None:
    # Given a natively built surmap-rtabmap-stream binary (CM5: no Docker)
    binary = tmp_path / "surmap-rtabmap-stream"
    binary.write_bytes(b"fake")
    binary.chmod(0o755)
    holder: list[FakeProcess] = []

    def factory(argv: list[str]) -> FakeProcess:
        proc = FakeProcess(argv)
        holder.append(proc)
        return proc

    # When the streaming backend is built for native launch
    backend = StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML,
        cam1_yaml=CAM_YAML,
        process_factory=factory,
        native_binary=binary,
    )
    try:
        # Then the child is the binary itself — no docker, no container
        assert holder[0].argv[0] == str(binary)
        assert "docker" not in holder[0].argv
        assert backend.live_containers == ()
    finally:
        backend.close()
    assert holder[0].terminated


def test_native_backend_never_computes_the_docker_image_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a native binary, and an image-tag computation that would
    # fail (an installed package cannot resolve the repo's deploy dir)
    binary = tmp_path / "surmap-rtabmap-stream"
    binary.write_bytes(b"fake")
    binary.chmod(0o755)

    def no_tag() -> str:
        raise AssertionError("native launch must not compute a Docker image tag")

    monkeypatch.setattr("surmap.slam.streaming.stream_image_tag", no_tag)

    # When the backend is built for native launch
    backend = StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML,
        cam1_yaml=CAM_YAML,
        process_factory=lambda argv: FakeProcess(argv),
        native_binary=binary,
    )

    # Then it starts without ever touching the Docker image path
    backend.close()


def test_native_backend_names_the_build_step_when_the_binary_is_missing(tmp_path: Path) -> None:
    # Given a native binary path that was never built
    # When the streaming backend is built for native launch
    # Then it fails by name, with the build step that produces the binary
    with pytest.raises(SidecarError, match="build_rtabmap_native"):
        StreamingRtabmapBackend(
            cam0_yaml=CAM_YAML,
            cam1_yaml=CAM_YAML,
            process_factory=lambda argv: FakeProcess(argv),
            native_binary=tmp_path / "surmap-rtabmap-stream",
        )


def test_poll_updates_ordering_and_snapshot_replaces_after_graph() -> None:
    holder: list[FakeProcess] = []
    backend = _backend(holder)
    try:
        backend.process_frame(_frame(1))
        fake = holder[0]
        fake.emit(
            {
                "type": "odom",
                "frame_id": 1,
                "t_ns": 1_000_000_000,
                "pose": [0, 0, 0, 0, 0, 0, 1],
                "lost": False,
                "ms": 5.0,
            }
        )
        fake.emit(
            {
                "type": "keyframe",
                "node_id": 1,
                "frame_id": 1,
                "t_ns": 1_000_000_000,
                "pose": [0, 0, 0, 0, 0, 0, 1],
                "points_local": [[1, 0, 0]],
            }
        )
        deadline = time.monotonic() + 5
        updates: list[object] = []
        while time.monotonic() < deadline and len(updates) < 2:
            updates.extend(backend.poll_updates())
            time.sleep(0.01)
        assert [type(u).__name__ for u in updates] == ["OdomUpdate", "KeyframeUpdate"]
        assert backend.map_snapshot() == (
            (__import__("surmap.types", fromlist=["Vec3"]).Vec3(1.0, 0.0, 0.0)),
        )

        # When a loop-closure graph moves node 1 to x=10
        fake.emit(
            {
                "type": "graph",
                "poses": [{"node_id": 1, "pose": [10, 0, 0, 0, 0, 0, 1]}],
                "final": False,
            }
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            backend.poll_updates()
            if backend.map_snapshot() and backend.map_snapshot()[0].x == 11.0:
                break
            time.sleep(0.01)
        assert backend.map_snapshot()[0].x == 11.0
        assert backend.trajectory()[0].position.x == 10.0
    finally:
        backend.close()


def test_keyframe_points_are_capped_so_snapshots_stay_bounded() -> None:
    holder: list[FakeProcess] = []
    backend = _backend(holder)
    try:
        backend.process_frame(_frame(1))
        holder[0].emit(
            {
                "type": "keyframe",
                "node_id": 1,
                "frame_id": 1,
                "t_ns": 1_000_000_000,
                "pose": [0, 0, 0, 0, 0, 0, 1],
                "points_local": [[float(i), 0, 0] for i in range(5000)],
            }
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not backend.map_snapshot():
            backend.poll_updates()
            time.sleep(0.01)
        backend.poll_updates()
        assert 0 < len(backend.map_snapshot()) <= 1000
    finally:
        backend.close()


def test_flush_shape_matches_batch_and_close_is_idempotent() -> None:
    holder: list[FakeProcess] = []
    rm_calls: list[list[str]] = []
    backend = _backend(holder, runner=lambda argv: rm_calls.append(argv))
    backend.process_frame(_frame(1))
    fake = holder[0]
    fake.emit(
        {
            "type": "odom",
            "frame_id": 1,
            "t_ns": 1_000_000_000,
            "pose": [1, 0, 0, 0, 0, 0, 1],
            "lost": False,
            "ms": 1.0,
        }
    )
    fake.emit(
        {
            "type": "keyframe",
            "node_id": 1,
            "frame_id": 1,
            "t_ns": 1_000_000_000,
            "pose": [1, 0, 0, 0, 0, 0, 1],
            "points_local": [[0, 0, 1]],
        }
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not backend.poll_updates() and True:
        # drain until keyframe applied via poll loop in backend state
        backend.poll_updates()
        if backend.map_snapshot():
            break
        time.sleep(0.01)
    results = backend.flush()
    assert [r.frame_id for r in results] == [1]
    assert results[0].pose is not None and results[0].static_points  # cloud on last
    backend.close()
    assert holder[0].terminated
    assert rm_calls and rm_calls[0][:3] == ["docker", "rm", "-f"]
    count = len(rm_calls)
    backend.close()
    assert len(rm_calls) == count  # idempotent


def test_shared_container_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SURMAP_RTABMAP_SHARED_CONTAINER", "reusable")
    with pytest.raises(SidecarError, match="shared"):
        _backend([])


def test_dockerfile_digest_matches_pinned_image() -> None:
    dockerfile = Path("deploy/rtabmap-stream/Dockerfile").read_text(encoding="utf-8")
    from surmap.slam.sidecar import PINNED_RTABMAP_IMAGE

    assert PINNED_RTABMAP_IMAGE in dockerfile


def _eventually(condition: Callable[[], bool], backend: StreamingRtabmapBackend) -> None:
    """Drain updates until the reader thread has applied what the test emitted."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        backend.poll_updates()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("condition never held")


def _keyframe(node_id: int, pose: list[float], points: list[list[float]]) -> dict[str, object]:
    return {
        "type": "keyframe",
        "node_id": node_id,
        "frame_id": node_id,
        "t_ns": node_id * 1_000_000_000,
        "pose": pose,
        "points_local": points,
    }


def _odom(frame_id: int, pose: list[float]) -> dict[str, object]:
    return {
        "type": "odom",
        "frame_id": frame_id,
        "t_ns": frame_id * 1_000_000_000,
        "pose": pose,
        "lost": False,
        "ms": 1.0,
    }


IDENTITY = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def test_keyframes_the_optimized_graph_dropped_leave_the_map() -> None:
    # Given two keyframes, of which RTAB-Map's graph keeps only node 1
    holder: list[FakeProcess] = []
    backend = _backend(holder)
    try:
        backend.process_frame(_frame(1))
        holder[0].emit(_keyframe(1, IDENTITY, [[1, 0, 0]]))
        holder[0].emit(_keyframe(2, IDENTITY, [[2, 0, 0]]))
        _eventually(lambda: backend.keyframe_count == 2, backend)

        # When the graph update arrives without node 2
        holder[0].emit(
            {"type": "graph", "poses": [{"node_id": 1, "pose": IDENTITY}], "final": False}
        )

        # Then node 2's points and count are gone
        _eventually(lambda: backend.keyframe_count == 1, backend)
        assert backend.map_snapshot() == (Vec3(1.0, 0.0, 0.0),)
    finally:
        backend.close()


def test_map_cloud_returns_map_frame_points_with_their_colours() -> None:
    # Given a keyframe 10 m along x holding one coloured point
    holder: list[FakeProcess] = []
    backend = _backend(holder)
    try:
        backend.process_frame(_frame(1))
        holder[0].emit(_keyframe(1, [10, 0, 0, 0, 0, 0, 1], [[1, 0, 0, 10, 20, 30]]))
        _eventually(lambda: backend.keyframe_count == 1, backend)

        # When the map cloud is read
        cloud = backend.map_cloud()

        # Then the point is placed by its keyframe pose and keeps its colour
        assert cloud.points.tolist() == [[11.0, 0.0, 0.0]]
        assert cloud.colors.tolist() == [[10, 20, 30]]
    finally:
        backend.close()


def test_frame_odometry_returns_that_frames_pose_and_keypoints() -> None:
    # Given odometry for frame 2 carrying one tracked keypoint
    holder: list[FakeProcess] = []
    backend = _backend(holder)
    try:
        backend.process_frame(_frame(1))
        holder[0].emit({**_odom(2, [0, 0, 1, 0, 0, 0, 1]), "keypoints": [[7, 10, 20, 3.5]]})
        _eventually(lambda: backend.frame_odometry(2) is not None, backend)

        # When frame 2's odometry is read
        odom = backend.frame_odometry(2)

        # Then it is that frame's pose and keypoints, and frame 1 has none yet
        assert odom is not None
        assert odom.pose == Pose(Vec3(0.0, 0.0, 1.0))
        assert odom.keypoints == (Keypoint(7, 10.0, 20.0, 3.5),)
        assert backend.frame_odometry(1) is None
    finally:
        backend.close()


def test_rectification_is_the_one_the_sidecar_announced() -> None:
    # Given a sidecar announcing its left camera's rectification
    announced = {
        "rotation": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "rectified": [200, 200, 100, 80],
        "raw": [210, 209, 101, 79],
        "distortion": [-0.28, 0.07, 0, 0],
    }
    backend = _backend([], ready={"rectification": announced})
    try:
        # When / Then the backend exposes it
        rectification = backend.rectification
        assert rectification is not None
        assert rectification.rectified == (200.0, 200.0, 100.0, 80.0)
        assert rectification.distortion == (-0.28, 0.07, 0.0, 0.0)
    finally:
        backend.close()


def test_pairs_travel_as_raw_gray8_at_the_configured_size() -> None:
    # Given a backend configured for 376x240 frames
    holder: list[FakeProcess] = []
    backend = _backend(holder)
    hello_length = len(holder[0].written)
    try:
        # When a pair is processed
        backend.process_frame(_frame(1))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and len(holder[0].written) == hello_length:
            time.sleep(0.01)

        # Then it is sent as raw gray8 bytes, one per pixel
        pair = bytes(holder[0].written[hello_length:])
        (header_length,) = struct.unpack("<I", pair[:4])
        header = json.loads(pair[4 : 4 + header_length])
        (left_length,) = struct.unpack("<I", pair[4 + header_length : 8 + header_length])
        assert header["encoding"] == "gray8"
        assert left_length == 376 * 240
    finally:
        backend.close()


def test_sidecar_runs_on_the_pinned_image_platform() -> None:
    # Given / When a backend starts its sidecar
    holder: list[FakeProcess] = []
    backend = _backend(holder)
    backend.close()

    # Then docker run asks for the pinned image's only platform
    argv = holder[0].argv
    assert argv[argv.index("--platform") + 1] == "linux/amd64"


def test_sidecar_image_builds_for_the_pinned_image_platform() -> None:
    # Given / When the build command is produced
    argv = stream_build_argv("surmap/rtabmap-stream:abc", Path("deploy/rtabmap-stream"))

    # Then it builds for the pinned image's only platform
    assert argv == [
        "docker",
        "build",
        "--platform",
        "linux/amd64",
        "-t",
        "surmap/rtabmap-stream:abc",
        "deploy/rtabmap-stream",
    ]


def _hello(fake: FakeProcess) -> dict[str, object]:
    (length,) = struct.unpack("<I", bytes(fake.written[:4]))
    hello: dict[str, object] = json.loads(bytes(fake.written[4 : 4 + length]))
    return hello


def test_hello_carries_the_keyframe_depth_cap() -> None:
    # Given a backend for a street scene, mapping out to 30 m
    holder: list[FakeProcess] = []

    def factory(argv: list[str]) -> FakeProcess:
        holder.append(FakeProcess(argv))
        return holder[-1]

    backend = StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, process_factory=factory, max_depth_m=30.0
    )
    backend.close()

    # When / Then the sidecar is told the cap in its hello
    assert _hello(holder[0])["max_depth_m"] == 30.0


def test_the_keyframe_depth_cap_defaults_to_thirty_metres() -> None:
    # Given / When a backend starts without a cap
    holder: list[FakeProcess] = []
    _backend(holder).close()

    # Then the hello carries the street-survey default, and the disparity floor
    assert _hello(holder[0])["max_depth_m"] == 30.0
    assert _hello(holder[0])["min_disparity_px"] == 2.0


class _StdoutClosed(FakeProcess):
    """The sidecar exits after ready, with no final graph."""

    def close_stdin(self) -> None:
        self.stdin_closed.set()
        self._lines.put(b"")


class _BrokenStdin(FakeProcess):
    """The sidecar's stdin closes once a pair is written."""

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self._writes = 0

    def write(self, data: bytes) -> None:
        self._writes += 1
        if self._writes > 1:
            raise BrokenPipeError("stdin closed")
        super().write(data)

    def close_stdin(self) -> None:
        self.stdin_closed.set()


def test_a_sidecar_that_closes_its_output_fails_before_the_flush_timeout() -> None:
    # Given a sidecar that announces ready and then closes stdout
    holder: list[FakeProcess] = []

    def factory(argv: list[str]) -> FakeProcess:
        proc = _StdoutClosed(argv)
        holder.append(proc)
        return proc

    backend = StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML,
        cam1_yaml=CAM_YAML,
        process_factory=factory,
        flush_timeout=3.0,
    )
    start = time.monotonic()
    try:
        # When the capture is flushed
        with pytest.raises(SidecarError, match="closed its output") as raised:
            backend.flush()
    finally:
        backend.close()

    # Then the failure names the closed sidecar and does not wait out the flush window
    assert "timed out" not in str(raised.value)
    assert time.monotonic() - start < 2.0


def test_a_sidecar_whose_stdin_breaks_fails_before_the_flush_timeout() -> None:
    # Given a sidecar that dies when the first pair is written
    def factory(argv: list[str]) -> FakeProcess:
        return _BrokenStdin(argv)

    backend = StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML,
        cam1_yaml=CAM_YAML,
        process_factory=factory,
        flush_timeout=3.0,
    )
    start = time.monotonic()
    try:
        backend.process_frame(_frame(1))

        # When the capture is flushed
        with pytest.raises(SidecarError, match="stdin closed") as raised:
            backend.flush()
    finally:
        backend.close()

    # Then the write error is reported and the flush window is not used up
    assert "timed out" not in str(raised.value)
    assert time.monotonic() - start < 2.0


def test_a_lost_frame_is_omitted_and_the_odometry_state_is_lost() -> None:
    # Given one tracked frame and a later frame whose odometry is lost
    holder: list[FakeProcess] = []
    backend = _backend(holder)
    try:
        backend.process_frame(_frame(1))
        backend.process_frame(_frame(2))
        holder[0].emit(_odom(1, IDENTITY))
        holder[0].emit(
            {
                "type": "odom",
                "frame_id": 2,
                "t_ns": 2_000_000_000,
                "pose": None,
                "lost": True,
                "ms": 1.0,
            }
        )
        _eventually(lambda: backend.odom_state == "lost", backend)

        # When the capture is flushed
        results = backend.flush()

        # Then only the tracked frame is returned, and it is not given an invented pose
        assert [result.frame_id for result in results] == [1]
        assert results[0].pose is not None
        assert backend.odom_state == "lost"
    finally:
        backend.close()


def test_a_sidecar_process_that_fills_stderr_still_yields_stdout() -> None:
    # Given a process that fills the stderr pipe before it writes stdout
    script = (
        "import sys\n"
        "sys.stderr.write('x' * 300000)\n"
        "sys.stderr.flush()\n"
        "sys.stdout.write('ready\\n')\n"
        "sys.stdout.flush()\n"
    )
    proc = _PopenProcess([sys.executable, "-c", script])
    received: dict[str, bytes] = {"line": b""}

    def read() -> None:
        received["line"] = proc.readline()

    thread = threading.Thread(target=read)
    thread.start()
    thread.join(2.0)
    try:
        # When stdout is read
        # Then the ready line arrives, instead of the process blocking on a full stderr pipe
        assert not thread.is_alive()
        assert received["line"] == b"ready\n"
    finally:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        proc.wait(timeout=2)


def test_the_disparity_filter_drops_far_points_and_keeps_near_ones() -> None:
    # Given the disaster rig and a 30 m cap with a 2 px floor
    fx = 381.36
    baseline_m = 0.07
    near = Vec3(0.2, 0.0, 5.0)
    noisy = Vec3(0.2, 0.0, 25.0)
    beyond_cap = Vec3(0.2, 0.0, 40.0)

    # When the camera-frame points are filtered
    kept = keep_confident_camera_points(
        (near, noisy, beyond_cap),
        fx=fx,
        baseline_m=baseline_m,
        max_depth_m=30.0,
        min_disparity_px=2.0,
    )

    # Then only the near point remains: 25 m is under 2 px, 40 m is past the cap
    assert kept == (near,)


def test_a_live_backend_stores_near_points_and_drops_noisy_far_ones() -> None:
    # Given a backend calibrated like the disaster stereo rig
    holder: list[FakeProcess] = []

    def factory(argv: list[str]) -> FakeProcess:
        proc = FakeProcess(argv)
        holder.append(proc)
        return proc

    backend = StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML,
        cam1_yaml=CAM_YAML,
        process_factory=factory,
        max_depth_m=30.0,
        min_disparity_px=2.0,
        fx=381.36,
        baseline_m=0.07,
    )
    try:
        backend.process_frame(_frame(1))
        holder[0].emit(
            _keyframe(1, IDENTITY, [[0.2, 0.0, 5.0], [0.2, 0.0, 25.0], [0.2, 0.0, 40.0]])
        )
        _eventually(lambda: backend.keyframe_count == 1, backend)

        # When the map is read
        snapshot = backend.map_snapshot()

        # Then the 5 m point is kept and the noisy and over-cap points are gone
        assert len(snapshot) == 1
        assert snapshot[0].z == pytest.approx(5.0)
    finally:
        backend.close()


def test_odometry_restarts_after_losing_track() -> None:
    # Given / When a backend starts its sidecar with default parameters
    holder: list[FakeProcess] = []
    _backend(holder).close()

    # Then RTAB-Map is told to reset odometry one frame after losing track
    # (its default, 0, never recovers: a single dropout ends tracking)
    argv = holder[0].argv
    params = {argv[i + 1] for i, arg in enumerate(argv) if arg == "--Param"}
    assert "Odom/ResetCountdown=1" in params
    assert "Rtabmap/DetectionRate=2" in params
