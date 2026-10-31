"""Demo: SAM regions' dense points become persistent surfaces in the 3D pane."""

import base64
import io
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image

from surmap.demo.history import RunHistoryStore
from surmap.demo.server import (
    MOVING_ALPHA,
    MOVING_COLOUR,
    SURFACE_ALPHA,
    SURFACE_COLOURS,
    CloudPose,
    DemoEvent,
    DemoPlayer,
    PlaybackControls,
    make_demo_server,
    render_cloud_view,
    surface_tint,
)
from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus
from surmap.slam.streaming import MapCloud
from surmap.types import Vec3
from tests.test_demo import _prepared_tiny
from tests.test_demo_regions import FakeRegionBackend, a_car_mask

JPEG = b"\xff\xd8fake-jpeg\xff\xd9"
# The fake region backend places every mask at these two points.
REGION_POINTS = [[1.0, 2.0, 3.0], [1.5, 2.0, 3.0]]
# The cloud view's empty-pixel colour, which a surface splat is blended over.
BACKGROUND = (10, 12, 14)


class DriftingRegionBackend(FakeRegionBackend):
    """Places the mask 50 cm further along x on every frame: a car driving past."""

    def region_points(self, query: RegionQuery, timeout: float = 5.0) -> RegionResult:
        self.region_queries.append(query)
        shift = 0.5 * (query.frame_id - 1)
        points = (Vec3(1.0 + shift, 2.0, 3.0), Vec3(1.5 + shift, 2.0, 3.0))
        return RegionResult(query.query_id, query.frame_id, query.channel, RegionStatus.OK, points)


def a_map_around_the_region(backend: FakeRegionBackend | None = None) -> FakeRegionBackend:
    backend = backend if backend is not None else FakeRegionBackend()
    corners = np.array([[0.0, 1.0, 2.0], [2.5, 3.0, 4.0]], np.float32)
    backend.cloud = MapCloud(corners, np.full((2, 3), 90, np.uint8))
    return backend


def play(
    tmp_path: Path, backend: FakeRegionBackend, controls: PlaybackControls | None = None
) -> list[DemoEvent]:
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=lambda: backend,
        sam_source=a_car_mask(),
        controls=controls,
    )
    return list(player.events())


def surface_events(events: list[DemoEvent]) -> list[DemoEvent]:
    return [event for event in events if event.kind == "surface"]


def only_surface(event: DemoEvent) -> dict[str, object]:
    surfaces = event.data["surfaces"]
    assert isinstance(surfaces, list) and len(surfaces) == 1
    surface = surfaces[0]
    assert isinstance(surface, dict)
    return surface


def draws_tint(png_b64: object, colour: tuple[int, int, int], alpha: float) -> bool:
    """Whether some pixel shows `colour` blended at `alpha` over the empty background."""
    return draws_colour(png_b64, surface_tint(colour, alpha, BACKGROUND))


def draws_colour(png_b64: object, colour: tuple[int, int, int]) -> bool:
    image = Image.open(io.BytesIO(base64.b64decode(str(png_b64))))
    pixels = np.array(image.convert("RGB"))
    return bool(np.any(np.all(pixels == np.array(colour), axis=2)))


def final_cloud_png(events: list[DemoEvent]) -> object:
    return next(event for event in events if event.kind == "final").data["cloud_png"]


@contextmanager
def a_running_console(tmp_path: Path, backend: FakeRegionBackend) -> Iterator[str]:
    server = make_demo_server(
        _prepared_tiny(tmp_path),
        host="127.0.0.1",
        port=0,
        sam_fake=True,
        sam_label="car",
        backend_factory=lambda: backend,
        history_db=tmp_path / "history.db",
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
    with urllib.request.urlopen(url, timeout=5) as response:
        loaded = json.loads(response.read())
    assert isinstance(loaded, dict)
    return loaded


def post_status(url: str, body: dict[str, object]) -> int:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)


def test_every_region_event_is_followed_by_a_surface_event_for_its_frame(tmp_path: Path) -> None:
    # Given a live map that places a SAM car mask on every frame
    backend = a_map_around_the_region()

    # When playback runs to the end
    events = play(tmp_path, backend)

    # Then each region is assigned to a surface, right after it
    kinds = [event.kind for event in events]
    assert [event.data["frame_id"] for event in surface_events(events)] == [1, 2]
    assert kinds.index("surface") == kinds.index("region") + 1


def test_the_same_object_on_the_next_frame_continues_its_surface(tmp_path: Path) -> None:
    # Given the car is placed at the same points on both frames
    backend = a_map_around_the_region()

    # When playback runs
    first, second = surface_events(play(tmp_path, backend))

    # Then frame 1 starts surface 1 and frame 2 continues it with nothing new
    assert first.data["surfaces"] == [
        {
            "surface_id": 1,
            "label": "car",
            "track_id": 1,
            "continued": False,
            "points": REGION_POINTS,
            "total_points": 2,
            "moving": False,
        }
    ]
    assert second.data["surfaces"] == [
        {
            "surface_id": 1,
            "label": "car",
            "track_id": 1,
            "continued": True,
            "points": [],
            "total_points": 2,
            "moving": False,
        }
    ]


def test_surfaces_are_persisted_per_run_and_survive_reopening_the_database(
    tmp_path: Path,
) -> None:
    # Given a run with surface 1 seen on frames 1 and 3 and surface 2 on frame 2
    store = RunHistoryStore(tmp_path / "history.db")
    run_id = store.create_run("tiny-test", "Tiny Test")
    store.record_surface(
        run_id,
        frame_id=1,
        surface_id=1,
        label="car",
        track_id=7,
        points=[[1.0, 2.0, 3.0]],
        moving=False,
    )
    store.record_surface(
        run_id,
        frame_id=2,
        surface_id=2,
        label="car",
        track_id=8,
        points=[[5.0, 2.0, 3.0]],
        moving=True,
    )
    store.record_surface(
        run_id,
        frame_id=3,
        surface_id=1,
        label="car",
        track_id=0,
        points=[[1.5, 2.0, 3.0]],
        moving=False,
    )
    store.close()

    # When the database is reopened
    reopened = RunHistoryStore(tmp_path / "history.db")

    # Then each surface has every point assigned to it up to the asked frame
    assert reopened.surfaces_at(run_id, 2) == [
        {"surface_id": 1, "label": "car", "moving": False, "points": [[1.0, 2.0, 3.0]]},
        {"surface_id": 2, "label": "car", "moving": True, "points": [[5.0, 2.0, 3.0]]},
    ]
    assert reopened.surfaces_at(run_id, 3)[0] == {
        "surface_id": 1,
        "label": "car",
        "moving": False,
        "points": [[1.0, 2.0, 3.0], [1.5, 2.0, 3.0]],
    }


def test_a_snapshot_carries_the_surfaces_accumulated_up_to_its_frame(tmp_path: Path) -> None:
    # Given a two-frame run whose second frame added surface 2
    store = RunHistoryStore(tmp_path / "history.db")
    run_id = store.create_run("tiny-test", "Tiny Test")
    for seq, frame_id in ((0, 1), (1, 2)):
        store.record_frame(
            run_id, index=seq, frame_id=frame_id, t_ns=frame_id, jpeg=JPEG, overlay=[], camera=None
        )
    store.record_surface(
        run_id,
        frame_id=1,
        surface_id=1,
        label="car",
        track_id=7,
        points=[[1.0, 2.0, 3.0]],
        moving=False,
    )
    store.record_surface(
        run_id,
        frame_id=2,
        surface_id=2,
        label="car",
        track_id=8,
        points=[[5.0, 2.0, 3.0]],
        moving=True,
    )

    # When the run is rewound to its first frame
    snapshot = store.snapshot_at(run_id, 0)

    # Then only the surface that existed then comes back
    assert snapshot is not None
    assert snapshot["surfaces"] == [
        {"surface_id": 1, "label": "car", "moving": False, "points": [[1.0, 2.0, 3.0]]}
    ]


def a_surface_render(moving: bool) -> str:
    no_cloud = np.zeros((0, 3), np.float32)
    bounds = (np.full(3, -5.0, np.float32), np.full(3, 5.0, np.float32))
    surface = np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]], np.float32)
    return render_cloud_view(
        no_cloud, np.zeros((0, 3), np.uint8), CloudPose(), bounds, surfaces=((1, surface, moving),)
    )


def test_the_cloud_view_draws_a_static_surface_translucent_in_its_surface_colour() -> None:
    # Given / When surface 1, static, is rendered
    png = a_surface_render(moving=False)

    # Then it is surface 1's colour, blended over what lies behind it
    assert draws_tint(png, SURFACE_COLOURS[1], SURFACE_ALPHA)
    assert not draws_colour(png, SURFACE_COLOURS[1])


def test_the_cloud_view_draws_a_moving_surface_as_a_red_more_opaque_smear() -> None:
    # Given / When surface 1, moving, is rendered
    png = a_surface_render(moving=True)

    # Then it is red, more opaque than a static surface, and not its surface colour
    assert MOVING_ALPHA > SURFACE_ALPHA
    assert draws_tint(png, MOVING_COLOUR, MOVING_ALPHA)
    assert not draws_tint(png, SURFACE_COLOURS[1], SURFACE_ALPHA)


def test_the_3d_pane_shows_the_surface_layer(tmp_path: Path) -> None:
    # Given a live map that places a SAM car mask
    backend = a_map_around_the_region()

    # When playback runs to the end
    events = play(tmp_path, backend)

    # Then the final 3D view draws surface 1
    assert draws_tint(final_cloud_png(events), SURFACE_COLOURS[1], SURFACE_ALPHA)


def test_a_hidden_surface_layer_is_not_drawn(tmp_path: Path) -> None:
    # Given the viewer turned the surface layer off
    backend = a_map_around_the_region()
    controls = PlaybackControls()
    controls.set_surfaces_visible(False)

    # When playback runs to the end
    events = play(tmp_path, backend, controls)

    # Then the surfaces are still assigned, but not drawn
    assert surface_events(events)
    assert not draws_tint(final_cloud_png(events), SURFACE_COLOURS[1], SURFACE_ALPHA)


def test_an_object_driving_past_becomes_a_red_smeared_surface_in_the_3d_pane(
    tmp_path: Path,
) -> None:
    # Given a live map where the car's mask lands 50 cm further on frame 2
    backend = a_map_around_the_region(DriftingRegionBackend())

    # When playback runs to the end
    events = play(tmp_path, backend)

    # Then frame 2 continues the same surface but marks it moving, and it is drawn red
    first, second = surface_events(events)
    first_surface, second_surface = only_surface(first), only_surface(second)
    assert (first_surface["surface_id"], first_surface["moving"]) == (1, False)
    assert (second_surface["surface_id"], second_surface["moving"]) == (1, True)
    assert draws_tint(final_cloud_png(events), MOVING_COLOUR, MOVING_ALPHA)


def test_toggling_the_surface_layer_re_renders_the_cloud() -> None:
    # Given playback controls showing surfaces
    controls = PlaybackControls()
    before = controls.cloud_version

    # When the viewer hides them
    controls.set_surfaces_visible(False)

    # Then the layer is hidden and the player re-renders
    assert controls.surfaces_visible is False
    assert controls.cloud_version > before


def test_the_server_persists_streamed_surfaces_for_scrubbing(tmp_path: Path) -> None:
    # Given the test console with the fake SAM over a live map
    backend = a_map_around_the_region()
    with a_running_console(tmp_path, backend) as base:
        # When a viewer plays the scene to the end
        with urllib.request.urlopen(f"{base}/stream", timeout=10) as response:
            body = response.read().decode()
        runs = get_json(f"{base}/runs")["runs"]
        assert isinstance(runs, list)
        run_id = str(runs[0]["run_id"])
        snapshot = get_json(f"{base}/runs/{run_id}/snapshot?seq=1")

    # Then surfaces streamed, and the rewound moment carries them
    assert body.count("event: surface") == 2
    assert snapshot["surfaces"] == [
        {"surface_id": 1, "label": "car", "moving": False, "points": REGION_POINTS}
    ]


def test_the_page_toggles_the_surface_layer_and_no_longer_posts_regions(tmp_path: Path) -> None:
    # Given the test console
    with a_running_console(tmp_path, a_map_around_the_region()) as base:
        # When the page loads, and a client posts each layer action with nothing playing
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            page = response.read().decode()
        surfaces_status = post_status(f"{base}/control", {"action": "cloud_surfaces"})
        regions_status = post_status(f"{base}/control", {"action": "cloud_regions"})

    # Then the page offers the surfaces toggle, which is a known action; regions are gone
    assert "cloud_surfaces" in page and "setRegionLayer" not in page
    assert (surfaces_status, regions_status) == (409, 400)


def test_the_page_calls_no_function_it_does_not_define(tmp_path: Path) -> None:
    # Given the test console page
    with a_running_console(tmp_path, a_map_around_the_region()) as base:
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            page = response.read().decode()

    # When the page's listener wiring runs, every helper it calls must
    # exist — a call to a removed helper throws and silently stops the
    # remaining listeners (frame, map, final) from ever registering
    assert "listenForRegions(" not in page
    assert "addEventListener('frame'" in page
    assert "addEventListener('map'" in page
