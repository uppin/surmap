"""Streaming backend: the region rig and journalled dense frames (fake process, no Docker)."""

import base64
import time
from collections.abc import Callable

from surmap.slam.dense import DenseFrame
from surmap.slam.streaming import StreamingRtabmapBackend
from tests.test_slam_stream_protocol_dense import a_disparity_png, a_region_rig_message
from tests.test_slam_streaming import CAM_YAML, FakeProcess, _hello


def eventually(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition never held"
        time.sleep(0.01)


def a_journalling_backend(holder: list[FakeProcess]) -> StreamingRtabmapBackend:
    def factory(argv: list[str]) -> FakeProcess:
        holder.append(FakeProcess(argv, {"region_rig": a_region_rig_message()}))
        return holder[-1]

    return StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, process_factory=factory, dense_journal=True
    )


def a_dense_line(frame_id: int) -> dict[str, object]:
    return {
        "type": "dense",
        "frame_id": frame_id,
        "t_ns": frame_id * 1_000_000_000,
        "channel": 0,
        "to_map": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        "disparity_png": base64.b64encode(a_disparity_png()).decode(),
    }


def test_a_journalling_backend_asks_the_sidecar_for_dense_lines() -> None:
    # Given a backend that journals the dense buffer
    holder: list[FakeProcess] = []
    backend = a_journalling_backend(holder)
    try:
        # Then its hello asks for it
        assert _hello(holder[0])["dense_journal"] is True
    finally:
        backend.close()


def test_the_backend_knows_the_rig_its_sidecar_answers_regions_with() -> None:
    # Given a sidecar that announced its region rig
    holder: list[FakeProcess] = []
    backend = a_journalling_backend(holder)
    try:
        # Then the backend holds it, ready to be journalled
        rig = backend.region_rig
        assert rig is not None and (rig.width, rig.height) == (376, 240)
    finally:
        backend.close()


def test_dense_frames_are_drained_once_in_the_order_the_sidecar_sent_them() -> None:
    # Given a sidecar that computed the dense buffer of frames 4 and 5
    holder: list[FakeProcess] = []
    backend = a_journalling_backend(holder)
    try:
        holder[0].emit(a_dense_line(4))
        holder[0].emit(a_dense_line(5))

        # When the journal drains them
        drained: list[DenseFrame] = []

        def drain() -> bool:
            drained.extend(backend.poll_dense())
            return len(drained) == 2

        eventually(drain)

        # Then each comes once, in order
        assert [frame.frame_id for frame in drained] == [4, 5]
        assert backend.poll_dense() == []
    finally:
        backend.close()
