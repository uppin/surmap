"""Streaming backend region queries with a fake process (no Docker)."""

import json
import struct
import threading
import time

import pytest

from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus
from surmap.slam.sidecar import SidecarError
from surmap.slam.streaming import StreamingRtabmapBackend
from surmap.types import Vec3
from tests.test_slam_streaming import CAM_YAML, FakeProcess, _backend, _frame, _hello


SQUARE = ((10.0, 10.0), (50.0, 10.0), (50.0, 50.0), (10.0, 50.0))


def a_region_query(query_id: int, frame_id: int = 3, channel: int = 0) -> RegionQuery:
    return RegionQuery(query_id, frame_id, channel, 376, 240, SQUARE)


def a_region_answer(query_id: int, points: list[list[float]]) -> dict[str, object]:
    return {
        "type": "region",
        "query_id": query_id,
        "frame_id": 3,
        "channel": 0,
        "status": "ok",
        "points": points,
    }


def _requests(written: bytes) -> list[dict[str, object]]:
    """Every framed request header the backend wrote, in order (payloads skipped)."""
    headers: list[dict[str, object]] = []
    offset = 0
    while offset < len(written):
        (length,) = struct.unpack("<I", written[offset : offset + 4])
        header: dict[str, object] = json.loads(written[offset + 4 : offset + 4 + length])
        offset += 4 + length
        headers.append(header)
        payloads = 2 if header["type"] == "pair" else 0
        for _ in range(payloads):
            (size,) = struct.unpack("<I", written[offset : offset + 4])
            offset += 4 + size
    return headers


class RegionAnsweringProcess(FakeProcess):
    """Answers each region request once every expected request has been asked.

    Answers go out in `answer_order`, so a test can make the sidecar
    reply out of the order the queries were asked.
    """

    def __init__(self, argv: list[str], answers: dict[int, dict[str, object]]) -> None:
        super().__init__(argv)
        self._answers = answers
        self.answer_order: list[int] = sorted(answers)
        self._asked: set[int] = set()
        self._lock = threading.Lock()

    def write(self, data: bytes) -> None:
        super().write(data)
        (length,) = struct.unpack("<I", data[:4])
        header = json.loads(data[4 : 4 + length])
        if header.get("type") != "region":
            return
        with self._lock:
            self._asked.add(int(header["query_id"]))
            if self._asked >= set(self._answers):
                for query_id in self.answer_order:
                    self.emit(self._answers[query_id])


def _answering_backend(
    holder: list[RegionAnsweringProcess],
    answers: dict[int, dict[str, object]],
    answer_order: list[int] | None = None,
) -> StreamingRtabmapBackend:
    def factory(argv: list[str]) -> RegionAnsweringProcess:
        process = RegionAnsweringProcess(argv, answers)
        if answer_order is not None:
            process.answer_order = answer_order
        holder.append(process)
        return process

    return StreamingRtabmapBackend(cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, process_factory=factory)


def test_a_region_query_returns_the_sidecars_answer_for_that_query() -> None:
    # Given a sidecar that answers query 5 with two map-frame points
    holder: list[RegionAnsweringProcess] = []
    backend = _answering_backend(holder, {5: a_region_answer(5, [[1, 2, 3], [1, 2, 4]])})
    try:
        # When frame 3's region is queried
        result = backend.region_points(a_region_query(5), timeout=5.0)

        # Then the answer is that query's points, and the sidecar was asked once
        assert result == RegionResult(
            5, 3, 0, RegionStatus.OK, (Vec3(1.0, 2.0, 3.0), Vec3(1.0, 2.0, 4.0))
        )
        regions = [r for r in _requests(bytes(holder[0].written)) if r["type"] == "region"]
        assert [r["query_id"] for r in regions] == [5]
    finally:
        backend.close()


def test_concurrent_region_queries_each_get_their_own_answer_even_out_of_order() -> None:
    # Given a sidecar that answers query 2 before query 1
    holder: list[RegionAnsweringProcess] = []
    answers = {1: a_region_answer(1, [[1, 1, 1]]), 2: a_region_answer(2, [[2, 2, 2]])}
    backend = _answering_backend(holder, answers, answer_order=[2, 1])
    results: dict[int, RegionResult] = {}
    try:
        # When both queries are asked from separate threads
        askers = [
            threading.Thread(
                target=lambda q=q: results.__setitem__(
                    q, backend.region_points(a_region_query(q), timeout=5.0)
                )
            )
            for q in (1, 2)
        ]
        for asker in askers:
            asker.start()
        for asker in askers:
            asker.join(timeout=5)

        # Then each query got its own points, never the other's
        assert results[1].points == (Vec3(1.0, 1.0, 1.0),)
        assert results[2].points == (Vec3(2.0, 2.0, 2.0),)
    finally:
        backend.close()


def test_a_region_query_the_sidecar_never_answers_fails_by_name() -> None:
    # Given a sidecar that never answers region queries
    holder: list[FakeProcess] = []
    backend = _backend(holder)
    try:
        # When / Then the query times out with an error naming it
        with pytest.raises(SidecarError, match="region query 8"):
            backend.region_points(a_region_query(8), timeout=0.2)
    finally:
        backend.close()


class GatedPairProcess(RegionAnsweringProcess):
    """The first pair write blocks until released, as a busy RTAB-Map would."""

    def __init__(self, argv: list[str], answers: dict[int, dict[str, object]]) -> None:
        super().__init__(argv, answers)
        self.first_pair_started = threading.Event()
        self.release = threading.Event()
        self._pairs = 0

    def write(self, data: bytes) -> None:
        (length,) = struct.unpack("<I", data[:4])
        if json.loads(data[4 : 4 + length]).get("type") == "pair":
            self._pairs += 1
            if self._pairs == 1:
                self.first_pair_started.set()
                self.release.wait(timeout=5)
        super().write(data)


def test_a_region_query_is_written_ahead_of_pairs_still_queued() -> None:
    # Given a sidecar busy with pair 1 while pair 2 waits in the queue
    holder: list[GatedPairProcess] = []

    def factory(argv: list[str]) -> GatedPairProcess:
        holder.append(GatedPairProcess(argv, {6: a_region_answer(6, [[0, 0, 1]])}))
        return holder[-1]

    backend = StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, process_factory=factory
    )
    try:
        backend.process_frame(_frame(1))
        assert holder[0].first_pair_started.wait(timeout=5)
        backend.process_frame(_frame(2))
        answer: list[RegionResult] = []
        asker = threading.Thread(
            target=lambda: answer.append(backend.region_points(a_region_query(6), timeout=5.0))
        )
        asker.start()

        # When the sidecar finishes pair 1
        time.sleep(0.05)
        holder[0].release.set()
        asker.join(timeout=5)

        # Then the region query went out before the queued pair 2, and was answered
        kinds = [
            (r["type"], r.get("frame_id", r.get("query_id")))
            for r in _requests(bytes(holder[0].written))
        ]
        assert kinds[1:] == [("pair", 1), ("region", 6), ("pair", 2)]
        assert answer[0].status is RegionStatus.OK
    finally:
        holder[0].release.set()
        backend.close()


def test_hello_carries_how_long_frames_stay_queryable() -> None:
    # Given a backend whose frames must stay queryable for 20 s
    holder: list[FakeProcess] = []

    def factory(argv: list[str]) -> FakeProcess:
        holder.append(FakeProcess(argv))
        return holder[-1]

    backend = StreamingRtabmapBackend(
        cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, process_factory=factory, region_buffer_s=20.0
    )
    backend.close()

    # When / Then the sidecar is told the ring length in its hello
    assert _hello(holder[0])["region_buffer_s"] == 20.0
