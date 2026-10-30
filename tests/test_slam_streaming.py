"""Streaming backend tests with a fake process (no Docker)."""

import io
import json
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from surmap.slam.sidecar import SidecarError
from surmap.slam.streaming import StreamingRtabmapBackend
from surmap.types import StereoFramePair

CAM_YAML = "sensor_type: camera\nresolution: [376, 240]\n"


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (8, 6), 128).save(buffer, format="PNG")
    return buffer.getvalue()


def _frame(frame_id: int) -> StereoFramePair:
    return StereoFramePair(frame_id, frame_id * 1_000_000_000, "l", "r", "cal", _png(), _png())


class FakeProcess:
    """Scripted process: test pushes stdout lines; stdin is recorded."""

    def __init__(self, argv: list[str]) -> None:
        self.argv = argv
        self.written = bytearray()
        self.stdin_closed = threading.Event()
        self.terminated = False
        self._lines: queue.Queue[bytes] = queue.Queue()
        self._lines.put(b'{"type":"ready","version":1}\n')

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
) -> StreamingRtabmapBackend:
    def factory(argv: list[str]) -> FakeProcess:
        proc = FakeProcess(argv)
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
