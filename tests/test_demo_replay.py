"""Replay a recorded run from its journal: no RTAB-Map, no SAM, regions and surfaces recomputed."""

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from surmap.demo.datasets import DISPLAY_HEIGHT, DISPLAY_WIDTH
from surmap.demo.history import RunHistoryStore
from surmap.demo.replay import JournalPlayer
from surmap.demo.server import DemoEvent, DemoPlayer, make_demo_server
from surmap.slam.dense import ChannelRig, DenseFrame, RegionRig, encode_disparity
from surmap.slam.regions import RegionQuery, RegionResult
from surmap.survey.sam import InMemoryVideoSamDetector, RawFrame, SamDetection
from surmap.survey.surfaces import SurfaceMap
from surmap.types import Pose, Vec3
from tests.test_demo import _prepared_tiny
from tests.test_demo_regions import MASK, FakeRegionBackend

FX = 200.0
BASELINE_M = 0.1
# A wall the journalled disparity puts at fx * b / d = 2 m (16 units per pixel).
WALL_DISPARITY = round(FX * BASELINE_M / 2.0 * 16)
# MASK spans x 10..60 and y 10..50 on the display image, edges included.
MASK_PIXELS = 51 * 41


def a_rig() -> RegionRig:
    identity = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    cx, cy = DISPLAY_WIDTH / 2, DISPLAY_HEIGHT / 2
    camera = (FX, 0.0, cx, 0.0, FX, cy, 0.0, 0.0, 1.0)
    left = (FX, 0.0, cx, 0.0, 0.0, FX, cy, 0.0, 0.0, 0.0, 1.0, 0.0)
    right = (FX, 0.0, cx, -FX * BASELINE_M, 0.0, FX, cy, 0.0, 0.0, 0.0, 1.0, 0.0)
    zero = (0.0, 0.0, 0.0, 0.0)
    return RegionRig(
        DISPLAY_WIDTH,
        DISPLAY_HEIGHT,
        BASELINE_M,
        30.0,
        (ChannelRig(camera, zero, identity, left), ChannelRig(camera, zero, identity, right)),
    )


class JournallingRegionBackend(FakeRegionBackend):
    """A sidecar double that, like the real one, journals a frame's disparity on its first query.

    Its live answers are the fake's two fixed points; its journalled
    disparity is a flat wall 2 m away. A replay that reads the journal
    therefore finds the wall, never the two points.
    """

    def __init__(self) -> None:
        super().__init__()
        self.region_rig: RegionRig | None = a_rig()
        self._dense: list[DenseFrame] = []
        self._journalled: set[tuple[int, int]] = set()

    def region_points(self, query: RegionQuery, timeout: float = 5.0) -> RegionResult:
        key = (query.frame_id, query.channel)
        if key not in self._journalled:
            self._journalled.add(key)
            wall = np.full((DISPLAY_HEIGHT, DISPLAY_WIDTH), WALL_DISPARITY, np.uint16)
            self._dense.append(
                DenseFrame(
                    query.frame_id,
                    query.frame_id * 1000,
                    query.channel,
                    Pose(Vec3(0.0, 0.0, 0.0)),
                    encode_disparity(wall),
                )
            )
        return super().region_points(query, timeout)

    def poll_dense(self) -> list[DenseFrame]:
        drained, self._dense = self._dense, []
        return drained


class CountingSam(InMemoryVideoSamDetector):
    def __init__(self) -> None:
        super().__init__((SamDetection("car", 0.9, (10.0, 10.0, 60.0, 50.0), MASK),))
        self.tracked = 0

    def track(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        self.tracked += 1
        return super().track(frame)


@dataclass
class Console:
    base: str
    store: RunHistoryStore
    sam: CountingSam
    backends: list[JournallingRegionBackend] = field(default_factory=list)

    def stream(self, query: str = "") -> list[tuple[str, dict[str, object]]]:
        with urllib.request.urlopen(f"{self.base}/stream{query}", timeout=20) as response:
            return sse_events(response.read().decode())

    def status_of(self, path: str) -> int:
        try:
            with urllib.request.urlopen(f"{self.base}{path}", timeout=20) as response:
                return int(response.status)
        except urllib.error.HTTPError as error:
            return int(error.code)

    def runs(self) -> list[dict[str, object]]:
        with urllib.request.urlopen(f"{self.base}/runs", timeout=5) as response:
            runs = json.loads(response.read())["runs"]
        assert isinstance(runs, list)
        return runs


def sse_events(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for chunk in body.split("\n\n"):
        lines = dict(line.split(": ", 1) for line in chunk.splitlines() if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


def kinds(events: list[tuple[str, dict[str, object]]], kind: str) -> list[dict[str, object]]:
    return [data for name, data in events if name == kind]


@contextmanager
def a_console(tmp_path: Path) -> Iterator[Console]:
    sam = CountingSam()
    store = RunHistoryStore(tmp_path / "history.db")
    backends: list[JournallingRegionBackend] = []

    def start_rtabmap() -> JournallingRegionBackend:
        backends.append(JournallingRegionBackend())
        return backends[-1]

    server = make_demo_server(
        _prepared_tiny(tmp_path),
        host="127.0.0.1",
        port=0,
        sam_source=sam,
        backend_factory=start_rtabmap,
        history_store=store,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = str(server.server_address[0]), int(server.server_address[1])
        yield Console(f"http://{host}:{port}", store, sam, backends)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def a_recorded_run(console: Console) -> str:
    events = console.stream()
    run_id = str(kinds(events, "run")[0]["run_id"])
    return run_id


def test_a_live_run_journals_the_rig_and_each_queried_frames_dense_buffer(tmp_path: Path) -> None:
    # Given a live playback whose sidecar journals its dense buffer
    backend = JournallingRegionBackend()
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=lambda: backend,
        sam_source=CountingSam(),
    )

    # When the two-frame scene plays
    events: list[DemoEvent] = list(player.events())

    # Then the rig is journalled once, and each SAM frame's disparity once
    assert [event.kind for event in events].count("rig") == 1
    dense = [event for event in events if event.kind == "dense"]
    assert [event.data["frame_id"] for event in dense] == [1, 2]


def test_a_recorded_run_replays_without_starting_rtabmap_or_sam(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        # Given a run recorded live with RTAB-Map and SAM
        run_id = a_recorded_run(console)
        sam_calls = console.sam.tracked

        # When it is replayed as fast as possible
        replay = console.stream(f"?replay={run_id}&speed=0")

        # Then its frames, SAM results, regions and surfaces stream again
        assert len(kinds(replay, "frame")) == 2
        assert len(kinds(replay, "sam")) == 2
        assert len(kinds(replay, "region")) == 2
        assert len(kinds(replay, "surface")) == 2
        assert len(kinds(replay, "final")) == 1
        # ... and neither RTAB-Map nor SAM ran for it
        assert len(console.backends) == 1
        assert console.sam.tracked == sam_calls


def test_replayed_regions_come_from_the_journalled_dense_buffer(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        # Given a run whose live regions were two points but whose disparity is a 2 m wall
        run_id = a_recorded_run(console)

        # When it is replayed
        region = kinds(console.stream(f"?replay={run_id}&speed=0"), "region")[0]

        # Then the replayed region is the wall under the SAM mask
        placed = region["regions"]
        assert isinstance(placed, list) and placed[0]["status"] == "ok"
        points = np.array(placed[0]["points"], np.float64)
        assert len(points) == MASK_PIXELS
        np.testing.assert_allclose(points[:, 2], 2.0, atol=1e-3)


def test_a_replay_is_recorded_as_a_new_run_of_its_source(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        # Given a recorded run
        run_id = a_recorded_run(console)

        # When it is replayed
        replay_id = kinds(console.stream(f"?replay={run_id}&speed=0"), "run")[0]["run_id"]

        # Then the replay is its own persisted run, naming its source
        replay = next(run for run in console.runs() if run["run_id"] == replay_id)
        assert replay["replay_of"] == run_id
        assert replay["frame_count"] == 2 and replay["replayable"] is True


def test_an_unknown_or_unjournalled_run_cannot_be_replayed(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        # Given a run recorded before journals existed
        legacy = console.store.create_run("tiny-test", "Tiny")

        # Then neither it nor an unknown run can be replayed
        assert console.status_of(f"/stream?replay={legacy}") == 404
        assert console.status_of("/stream?replay=nope") == 404


def test_replay_assigns_surfaces_with_the_surface_logic_it_is_given(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        # Given a recorded run, and the surface logic under tuning
        run_id = a_recorded_run(console)
        tuned = SurfaceMap(voxel_m=0.05)

        # When it is replayed with that logic
        events = list(JournalPlayer(console.store, run_id, surfaces=tuned).events())

        # Then the replayed surfaces are that logic's
        assert [event.kind for event in events].count("surface") == 2
        assert len(tuned.surfaces()) == 1


def test_the_console_page_offers_to_replay_a_persisted_run(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        with urllib.request.urlopen(f"{console.base}/", timeout=5) as response:
            page = response.read().decode()

    assert 'id="run-replay"' in page
    assert "/stream?replay=" in page
