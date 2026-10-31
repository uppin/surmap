"""Demo: each SAM mask's region is placed in 3D and drawn on the cloud pane."""

import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from surmap.demo.datasets import DISPLAY_HEIGHT, DISPLAY_WIDTH
from surmap.demo.server import DemoEvent, DemoPlayer, make_demo_server
from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus
from surmap.survey.sam import InMemoryVideoSamDetector, SamDetection
from surmap.types import Vec3
from tests.test_demo import FakeLiveBackend, _prepared_tiny

MASK = ((10.0, 10.0), (60.0, 10.0), (60.0, 50.0), (10.0, 50.0))


class FakeRegionBackend(FakeLiveBackend):
    """Live backend double that also answers region queries with fixed points."""

    def __init__(self, status: RegionStatus = RegionStatus.OK) -> None:
        super().__init__()
        self._status = status
        self.region_queries: list[RegionQuery] = []

    def region_points(self, query: RegionQuery, timeout: float = 5.0) -> RegionResult:
        self.region_queries.append(query)
        points = (
            (Vec3(1.0, 2.0, 3.0), Vec3(1.5, 2.0, 3.0)) if self._status is RegionStatus.OK else ()
        )
        return RegionResult(query.query_id, query.frame_id, query.channel, self._status, points)


def a_car_mask() -> InMemoryVideoSamDetector:
    return InMemoryVideoSamDetector((SamDetection("car", 0.9, (10.0, 10.0, 60.0, 50.0), MASK),))


def play(tmp_path: Path, backend: FakeRegionBackend) -> list[DemoEvent]:
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=lambda: backend,
        sam_source=a_car_mask(),
    )
    return list(player.events())


def test_every_sam_result_is_followed_by_its_regions_points(tmp_path: Path) -> None:
    # Given a live map and a SAM source that outlines a car on every frame
    backend = FakeRegionBackend()

    # When playback runs to the end
    events = play(tmp_path, backend)

    # Then each frame's SAM event is followed by a region event for that frame
    sam_frames = [event.data["frame_id"] for event in events if event.kind == "sam"]
    region_events = [event for event in events if event.kind == "region"]
    assert [event.data["frame_id"] for event in region_events] == sam_frames == [1, 2]
    kinds = [event.kind for event in events]
    assert kinds.index("region") > kinds.index("sam")


def test_a_region_event_carries_each_masks_map_frame_points(tmp_path: Path) -> None:
    # Given a live map and a SAM source that outlines a car
    backend = FakeRegionBackend()

    # When playback runs
    region = next(event for event in play(tmp_path, backend) if event.kind == "region")

    # Then the car's region carries its track, label, status and points
    assert region.data["regions"] == [
        {
            "track_id": 1,
            "label": "car",
            "status": "ok",
            "points": [[1.0, 2.0, 3.0], [1.5, 2.0, 3.0]],
        }
    ]


def test_regions_are_asked_on_the_left_channel_at_the_display_size(tmp_path: Path) -> None:
    # Given SAM segments the left display image
    backend = FakeRegionBackend()

    # When playback runs
    play(tmp_path, backend)

    # Then each query names frame, channel 0, the display size and SAM's polygon
    first = backend.region_queries[0]
    assert (first.frame_id, first.channel) == (1, 0)
    assert (first.width, first.height) == (DISPLAY_WIDTH, DISPLAY_HEIGHT)
    assert first.polygon == MASK
    assert len({query.query_id for query in backend.region_queries}) == 2


def test_a_region_that_could_not_be_placed_keeps_its_reason_and_no_points(
    tmp_path: Path,
) -> None:
    # Given a map whose frames have already left the ring
    backend = FakeRegionBackend(RegionStatus.FRAME_EXPIRED)

    # When playback runs
    region = next(event for event in play(tmp_path, backend) if event.kind == "region")

    # Then the region is reported expired, with nothing drawn
    assert region.data["regions"] == [
        {"track_id": 1, "label": "car", "status": "expired", "points": []}
    ]


def test_without_a_live_map_sam_results_get_no_region(tmp_path: Path) -> None:
    # Given SAM but no RTAB-Map
    player = DemoPlayer(
        _prepared_tiny(tmp_path), fps=1000.0, with_rtabmap=False, sam_source=a_car_mask()
    )

    # When playback runs
    kinds = [event.kind for event in player.events()]

    # Then there is no depth to place a region with
    assert "sam" in kinds and "region" not in kinds


def test_the_fake_sam_drives_regions_and_the_surface_layer_onto_the_3d_pane(tmp_path: Path) -> None:
    # Given a demo server with the fake SAM and a live map
    backend = FakeRegionBackend()
    server = make_demo_server(
        _prepared_tiny(tmp_path),
        host="127.0.0.1",
        port=0,
        sam_fake=True,
        backend_factory=lambda: backend,
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

    # Then SAM and region events stream, and the 3D pane offers the surface layer
    assert body.count("event: sam") == 2
    assert body.count("event: region") == 2
    assert "cloud_surfaces" in page


def test_the_demo_cli_offers_a_fake_sam() -> None:
    # Given / When the launcher is asked for its help
    result = subprocess.run(
        [sys.executable, "scripts/demo.py", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    # Then the fake SAM switch is listed
    assert result.returncode == 0
    assert "--sam-fake" in result.stdout
