"""Demo scene picker (download on first pick, with progress) and playback controls."""

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from surmap.demo.datasets import (
    DatasetSpec,
    PrepareProgress,
    ZipAsset,
    cached_dataset,
    ensure_dataset,
)
from surmap.demo.server import DemoEvent, DemoPlayer, PlaybackControls, make_demo_server
from surmap.slam.base import FrameResult
from surmap.types import StereoFramePair
from tests.test_demo import FakeLiveBackend, _odom_with, _prepared_tiny
from tests.test_demo_kitti import a_kitti_drive


class CountingBackend(FakeLiveBackend):
    """Live backend double that records which frames reached SLAM."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[int] = []

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self.sent.append(frame.frame_id)
        return super().process_frame(frame)


def a_local_scene(tmp_path: Path, scene_id: str) -> DatasetSpec:
    """A two-frame KITTI-format scene whose zips are served from local files."""
    folder = tmp_path / scene_id
    folder.mkdir()
    spec, sources = a_kitti_drive(folder)
    assert spec.calibration is not None
    drive = sources[spec.zip_url]
    calibration = sources[spec.calibration.url]
    return replace(
        spec,
        dataset_id=scene_id,
        title=f"Scene {scene_id}",
        zip_url=drive.as_uri(),
        calibration=ZipAsset(
            calibration.as_uri(), spec.calibration.size_bytes, spec.calibration.sha256
        ),
    )


def eventually(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError("condition never held")


@contextmanager
def a_demo_server(catalog: list[DatasetSpec], cache: Path, fps: float = 50.0) -> Iterator[str]:
    server = make_demo_server(
        catalog=catalog,
        cache_dir=cache,
        default_dataset=catalog[0].dataset_id,
        host="127.0.0.1",
        port=0,
        fps=fps,
        with_rtabmap=False,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = str(server.server_address[0]), int(server.server_address[1])
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        loaded: dict[str, object] = json.loads(response.read())
        return loaded


def post_json(url: str, body: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body or {}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, {}


def status_of(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)


def scene_state(base: str, scene_id: str) -> dict[str, object]:
    listing = get_json(f"{base}/datasets")
    scenes = listing["datasets"]
    assert isinstance(scenes, list)
    found: dict[str, object] = next(scene for scene in scenes if scene["id"] == scene_id)
    return found


def stream_kinds(url: str, out: "queue.Queue[str]") -> None:
    """Push each SSE event kind from `url` onto `out`, then "end"."""
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            for raw in response:
                line = raw.decode().strip()
                if line.startswith("event: "):
                    out.put(line.removeprefix("event: "))
    except (urllib.error.URLError, ConnectionError):
        pass
    out.put("end")


def test_an_already_prepared_scene_is_found_without_downloading(tmp_path: Path) -> None:
    # Given a scene prepared once into the cache
    spec = a_local_scene(tmp_path, "street")
    ensure_dataset(spec, tmp_path / "cache", log=lambda _: None)
    assert (
        cached_dataset(replace(spec, zip_url="file:///nowhere.zip"), tmp_path / "missing") is None
    )

    # When it is looked up with its source gone
    found = cached_dataset(replace(spec, zip_url="file:///nowhere.zip"), tmp_path / "cache")

    # Then the cached copy is used
    assert found is not None and len(found.timestamps_ns) == 2


def test_preparing_reports_download_bytes_then_extracted_files(tmp_path: Path) -> None:
    # Given a scene not yet in the cache
    spec = a_local_scene(tmp_path, "street")
    reports: list[PrepareProgress] = []

    # When it is prepared with a progress listener
    ensure_dataset(spec, tmp_path / "cache", log=lambda _: None, progress=reports.append)

    # Then it reports the drive's bytes downloaded, verification, every
    # extracted file, and finally ready
    phases = [report.phase for report in reports]
    assert phases[0] == "downloading" and phases[-1] == "ready"
    assert "verifying" in phases
    downloads = [report for report in reports if report.phase == "downloading"]
    assert any(r.done == r.total == spec.zip_size_bytes for r in downloads)
    extracted = [report for report in reports if report.phase == "extracting"]
    assert extracted[-1].done == extracted[-1].total == 4  # 2 pairs x 2 cameras


def test_every_scene_is_listed_with_its_state_and_the_current_one(tmp_path: Path) -> None:
    # Given two scenes, neither downloaded
    catalog = [a_local_scene(tmp_path, "street"), a_local_scene(tmp_path, "room")]

    with a_demo_server(catalog, tmp_path / "cache") as base:
        # When the scene list is read
        listing = get_json(f"{base}/datasets")

    # Then both are offered, both missing, the first current
    assert listing["current"] == "street"
    scenes = listing["datasets"]
    assert isinstance(scenes, list)
    assert [(s["id"], s["title"], s["state"]) for s in scenes] == [
        ("street", "Scene street", "missing"),
        ("room", "Scene room", "missing"),
    ]


def test_picking_a_missing_scene_prepares_it_in_the_background(tmp_path: Path) -> None:
    # Given a scene not yet downloaded
    catalog = [a_local_scene(tmp_path, "street")]

    with a_demo_server(catalog, tmp_path / "cache") as base:
        # When its preparation is requested
        status, body = post_json(f"{base}/prepare?dataset=street")

        # Then it is accepted, and the listing reaches ready with its progress
        assert status == 202 and body["state"] in ("preparing", "ready")
        eventually(lambda: scene_state(base, "street")["state"] == "ready")
        assert scene_state(base, "street")["progress"] == {"phase": "ready", "done": 1, "total": 1}


def test_a_scene_prepared_once_is_cached_for_the_next_server(tmp_path: Path) -> None:
    # Given a scene prepared by one server, whose source then disappears
    scene = a_local_scene(tmp_path, "street")
    with a_demo_server([scene], tmp_path / "cache") as base:
        post_json(f"{base}/prepare?dataset=street")
        eventually(lambda: scene_state(base, "street")["state"] == "ready")
    Path(scene.zip_url.removeprefix("file://")).unlink()

    # When a new server starts over the same cache
    with a_demo_server([scene], tmp_path / "cache") as base:
        # Then the scene is ready at once, without fetching
        assert scene_state(base, "street")["state"] == "ready"


def test_any_scene_page_is_served_but_only_prepared_scenes_stream(tmp_path: Path) -> None:
    # Given two scenes of which only "street" is prepared
    catalog = [a_local_scene(tmp_path, "street"), a_local_scene(tmp_path, "room")]
    ensure_dataset(catalog[0], tmp_path / "cache", log=lambda _: None)

    with a_demo_server(catalog, tmp_path / "cache") as base:
        # When / Then "room"'s page renders, its stream waits for preparation,
        # unknown scenes are not found, and "street" streams
        with urllib.request.urlopen(f"{base}/?dataset=room", timeout=10) as response:
            assert "Scene room" in response.read().decode()
        assert status_of(f"{base}/stream?dataset=room") == 409
        assert status_of(f"{base}/?dataset=nope") == 404
        with urllib.request.urlopen(f"{base}/stream?dataset=street", timeout=10) as response:
            assert response.read().decode().count("event: frame") == 2


def test_a_new_viewer_takes_the_stream_over(tmp_path: Path) -> None:
    # Given a slow stream already playing to a first viewer
    catalog = [a_local_scene(tmp_path, "street")]
    ensure_dataset(catalog[0], tmp_path / "cache", log=lambda _: None)
    with a_demo_server(catalog, tmp_path / "cache", fps=1.0) as base:
        first: queue.Queue[str] = queue.Queue()
        threading.Thread(target=stream_kinds, args=(f"{base}/stream", first), daemon=True).start()
        assert first.get(timeout=10) == "frame"

        # When a second viewer opens the stream
        second: queue.Queue[str] = queue.Queue()
        threading.Thread(target=stream_kinds, args=(f"{base}/stream", second), daemon=True).start()

        # Then the second gets frames and the first stream ends
        assert second.get(timeout=10) == "frame"
        assert first.get(timeout=10) == "end"


def test_control_pauses_and_resumes_the_running_stream(tmp_path: Path) -> None:
    # Given a slow stream playing
    catalog = [a_local_scene(tmp_path, "street")]
    ensure_dataset(catalog[0], tmp_path / "cache", log=lambda _: None)
    with a_demo_server(catalog, tmp_path / "cache", fps=2.0) as base:
        # (with nothing playing yet there is nothing to control)
        assert post_json(f"{base}/control", {"action": "pause"})[0] == 409
        events: queue.Queue[str] = queue.Queue()
        threading.Thread(target=stream_kinds, args=(f"{base}/stream", events), daemon=True).start()
        assert events.get(timeout=10) == "frame"

        # When it is paused, then resumed
        assert post_json(f"{base}/control", {"action": "pause"}) == (200, {"state": "paused"})
        with pytest.raises(queue.Empty):
            events.get(timeout=1.0)
        assert post_json(f"{base}/control", {"action": "resume"}) == (200, {"state": "playing"})

        # Then playback carries on, and unknown actions are refused
        assert events.get(timeout=10) == "frame"
        assert post_json(f"{base}/control", {"action": "rewind"})[0] == 400


def test_paused_playback_shows_no_frames_and_feeds_no_pairs(tmp_path: Path) -> None:
    # Given a player paused before it starts
    fake = CountingBackend()
    controls = PlaybackControls()
    controls.pause()
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=lambda: fake,
        controls=controls,
    )
    events: queue.Queue[DemoEvent] = queue.Queue()

    def play() -> None:
        for event in player.events():
            events.put(event)

    threading.Thread(target=play, daemon=True).start()

    # When it stays paused for a while
    time.sleep(0.5)

    # Then nothing was shown or sent to SLAM, until it is resumed
    assert events.empty() and fake.sent == []
    controls.resume()
    assert events.get(timeout=10).kind in ("frame", "map")
    eventually(lambda: fake.sent == [1, 2])


def test_a_cancelled_player_stops_and_closes_its_backend(tmp_path: Path) -> None:
    # Given a live player whose frames each get their odometry at once
    fake = FakeLiveBackend(odometry={1: _odom_with(), 2: _odom_with()})
    controls = PlaybackControls()
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=lambda: fake,
        controls=controls,
    )

    # When it is cancelled after its first frame
    kinds = []
    for event in player.events():
        kinds.append(event.kind)
        if event.kind == "frame":
            controls.cancel()

    # Then it stopped without finishing the drive, and tore its backend down
    assert kinds.count("frame") == 1 and "final" not in kinds
    assert fake.closed
