"""Demo: the 3D pane follows the camera like a navigation app (checked "Follow")."""

import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.demo.cloud_view import CAMERA_MARKER, CloudPose, CloudViewer, FollowCamera
from surmap.demo.history import RunHistoryStore
from surmap.demo.replay import Bounds, CloudRenderer, JournalPlayer
from surmap.demo.runs import PlaybackControls
from surmap.demo.server import DemoPlayer
from surmap.demo.surface_render import SurfaceLayer
from surmap.types import Pose, Vec3
from tests.test_demo import _odom_with, _prepared_tiny
from tests.test_demo_cloud_pick import decode, ids_of
from tests.test_demo_cloud_ptz import play_to_the_end, post
from tests.test_demo_object_feed import a_console_page
from tests.test_demo_regions import FakeRegionBackend, a_car_mask
from tests.test_demo_replay_sam import JPEG
from tests.test_demo_surfaces import a_map_around_the_region, a_running_console

# A 60 m square of grey map around the origin, on the ground (y = 1.5, y points down).
GROUND = np.array(
    [[x, 1.5, z] for x in np.linspace(-30, 30, 31) for z in np.linspace(-30, 30, 31)], np.float32
)
GREY = np.full((len(GROUND), 3), 120, np.uint8)
BOUNDS = (GROUND.min(axis=0), GROUND.max(axis=0))
HEIGHT, WIDTH = 440, 880  # the cloud view's size


def a_probe(x: float, z: float) -> NDArray[np.float32]:
    """A small upright patch of points at (x, z): a marker surface."""
    return np.array(
        [
            [x + dx, dy, z + dz]
            for dx in (-0.2, 0, 0.2)
            for dy in (-0.2, 0, 0.2)
            for dz in (-0.2, 0, 0.2)
        ],
        np.float32,
    )


def a_camera(x: float, z: float, dx: float, dz: float) -> FollowCamera:
    return {"x": x, "z": z, "dx": dx, "dz": dz, "fov_deg": 78.8}


def where(ids: NDArray[np.int64], surface_id: int) -> tuple[float, float]:
    """The (u, v) centre of a probe in the id image."""
    rows, columns = np.nonzero(ids == surface_id)
    assert len(rows), f"probe {surface_id} is out of view"
    return float(columns.mean()), float(rows.mean())


def probes_seen(
    viewer: CloudViewer, camera: FollowCamera | None, layer: SurfaceLayer
) -> NDArray[np.int64]:
    return ids_of(viewer.render_view(GROUND, GREY, BOUNDS, layer, camera)["cloud_ids_png"])


@pytest.mark.parametrize(
    ("camera", "ahead", "right"),
    [
        # Looking along +z: ahead is +z, its right is +x
        (a_camera(0.0, 0.0, 0.0, 1.0), (0.0, 10.0), (4.0, 0.0)),
        # Looking along +x from (5, -2): ahead is +x, its right is -z
        (a_camera(5.0, -2.0, 1.0, 0.0), (15.0, -2.0), (5.0, -6.0)),
    ],
)
def test_following_looks_the_way_the_camera_looks_from_behind_and_above(
    camera: FollowCamera, ahead: tuple[float, float], right: tuple[float, float]
) -> None:
    # Given probes at the camera, 10 m ahead of it and 4 m to its right
    layer: SurfaceLayer = (
        (1, a_probe(camera["x"], camera["z"]), False),
        (2, a_probe(*ahead), False),
        (3, a_probe(*right), False),
    )

    # When the view follows the camera
    ids = probes_seen(CloudViewer(), camera, layer)

    # Then the camera sits low and centred, with a quarter of the view behind it,
    # what is ahead is up the view, and what is on its right is on the right
    camera_u, camera_v = where(ids, 1)
    assert camera_u == pytest.approx(WIDTH / 2, abs=0.03 * WIDTH)
    assert 0.70 * HEIGHT <= camera_v <= 0.80 * HEIGHT
    assert where(ids, 2)[1] < camera_v - 20
    assert where(ids, 3)[0] > camera_u + 20


def test_the_view_follows_by_default() -> None:
    assert CloudViewer().follow is True


def test_without_a_camera_the_follow_view_is_the_free_view() -> None:
    # Given one viewer following and one not
    following, free = CloudViewer(), CloudViewer()
    free.set_follow(False)

    # When both draw a scene that has no camera
    layer: SurfaceLayer = ((1, a_probe(0.0, 0.0), False),)

    # Then they draw the same thing
    assert following.render_view(GROUND, GREY, BOUNDS, layer, None) == free.render_view(
        GROUND, GREY, BOUNDS, layer, None
    )


def test_the_free_view_is_not_mirrored() -> None:
    # Given a free view from behind the origin, looking along +z
    viewer = CloudViewer()
    viewer.set_follow(False)
    viewer.reset()
    viewer.orbit(math.pi - CloudPose().azimuth, 0.0)

    # When probes 4 m either side are drawn
    ids = probes_seen(viewer, None, ((1, a_probe(-4.0, 0.0), False), (2, a_probe(4.0, 0.0), False)))

    # Then +x (the right of a camera looking along +z) is on the right
    assert where(ids, 2)[0] > where(ids, 1)[0]


def gap(ids: NDArray[np.int64]) -> float:
    """How far up the view the probe ahead (2) is drawn above the camera's (1)."""
    return where(ids, 1)[1] - where(ids, 2)[1]


AHEAD_OF_CAMERA: SurfaceLayer = ((1, a_probe(0.0, 0.0), False), (2, a_probe(0.0, 6.0), False))
CAMERA_ALONG_Z = a_camera(0.0, 0.0, 0.0, 1.0)


def camera_row(ids: NDArray[np.int64]) -> float:
    """How far down the view the camera's probe (1) sits, as a fraction of its height."""
    return where(ids, 1)[1] / HEIGHT


def test_tilting_keeps_following_with_the_camera_low_in_view() -> None:
    # Given a view following a camera along +z
    viewer = CloudViewer()
    before = probes_seen(viewer, CAMERA_ALONG_Z, AHEAD_OF_CAMERA)

    # When the viewer tilts up
    viewer.orbit(0.0, 0.3)
    tilted = probes_seen(viewer, CAMERA_ALONG_Z, AHEAD_OF_CAMERA)

    # Then it still follows, the camera still at 3/4 of the view, and the view changed
    assert viewer.follow is True
    assert camera_row(tilted) == pytest.approx(0.75, abs=0.05)
    assert gap(tilted) != pytest.approx(gap(before), abs=1.0)


def test_zooming_in_keeps_following_and_brings_what_is_ahead_closer() -> None:
    # Given a view following a camera along +z
    viewer = CloudViewer()
    before = probes_seen(viewer, CAMERA_ALONG_Z, AHEAD_OF_CAMERA)

    # When the viewer zooms in
    viewer.zoom(0.6)
    zoomed = probes_seen(viewer, CAMERA_ALONG_Z, AHEAD_OF_CAMERA)

    # Then it still follows with the camera low in view, and the probe ahead is drawn further up
    assert viewer.follow is True
    assert camera_row(zoomed) == pytest.approx(0.75, abs=0.05)
    assert gap(zoomed) > gap(before)


def test_orbiting_takes_over_from_follow() -> None:
    # Given a following view
    viewer = CloudViewer()

    # When the viewer orbits it
    viewer.orbit(0.2, 0.0)

    # Then the view no longer follows
    assert viewer.follow is False


def test_panning_takes_over_from_follow() -> None:
    # Given a following view
    viewer = CloudViewer()

    # When the viewer pans it
    viewer.pan(1.0, 0.0)

    # Then the view no longer follows
    assert viewer.follow is False


def test_taking_over_starts_from_the_follow_view_without_a_jump() -> None:
    # Given a view following a camera looking along +x
    camera = a_camera(5.0, -2.0, 1.0, 0.0)
    layer: SurfaceLayer = ((1, a_probe(5.0, -2.0), False), (2, a_probe(15.0, -2.0), False))
    viewer = CloudViewer()
    following = probes_seen(viewer, camera, layer)

    # When the viewer takes over with a pan of nothing
    viewer.pan(0.0, 0.0)
    taken = probes_seen(viewer, camera, layer)

    # Then the free view draws both probes exactly where the follow view did
    assert viewer.follow is False
    assert [*where(taken, 1), *where(taken, 2)] == pytest.approx(
        [*where(following, 1), *where(following, 2)], abs=2.0
    )


def marked(png: str) -> bool:
    """Whether the image shows the camera marker's colour anywhere."""
    rgb = decode(png)[..., :3]
    return bool(np.any(np.all(rgb == np.array(CAMERA_MARKER), axis=2)))


def test_the_camera_is_marked_in_a_view_drawn_for_it() -> None:
    # When a view is drawn for a camera
    view = CloudViewer().render_view(GROUND, GREY, BOUNDS, (), a_camera(0, 0, 0, 1))

    # Then the camera is marked in it
    assert marked(view["cloud_png"])


def test_a_view_without_a_camera_has_no_marker() -> None:
    # When a view is drawn with no camera
    view = CloudViewer().render_view(GROUND, GREY, BOUNDS, (), None)

    # Then nothing is marked
    assert not marked(view["cloud_png"])


@pytest.mark.parametrize(
    ("body", "follows"),
    [
        ({"action": "cloud_zoom", "factor": 0.9}, True),
        ({"action": "cloud_follow", "follow": False}, False),
        ({"action": "cloud_follow", "follow": True}, True),
        ({"action": "cloud_orbit", "d_azimuth": 0.3}, False),
    ],
)
def test_a_ptz_answer_says_whether_the_view_follows(
    tmp_path: Path, body: dict[str, object], follows: bool
) -> None:
    # Given a console's view, following by default
    with a_running_console(tmp_path, a_map_around_the_region(FakeRegionBackend())) as base:
        # When one PTZ action is posted
        answer = post(f"{base}/control", body)[1]

    # Then the answer says whether the view follows now
    assert answer["follow"] is follows


def a_driving_map() -> FakeRegionBackend:
    """A live map whose camera moves 1 m along +z per frame."""
    odometry = {n: _odom_with(pose=Pose(Vec3(0.0, 0.0, float(n)))) for n in (1, 2)}
    return a_map_around_the_region(FakeRegionBackend(odometry=odometry))


def test_the_live_view_is_drawn_for_the_shown_frames_camera(tmp_path: Path) -> None:
    # When a live run plays
    controls = PlaybackControls()
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        backend_factory=a_driving_map,
        sam_source=a_car_mask(),
        controls=controls,
    )
    frames = [event for event in player.events() if event.kind == "frame"]

    # Then its last view was drawn for the last frame's camera
    assert frames and frames[-1].data["camera"] is not None
    assert controls.viewer.camera == frames[-1].data["camera"]


def a_recorded_drive(store: RunHistoryStore, frames: int = 3) -> str:
    """A recorded run whose camera moves 1 m along +z per frame, one map update per frame."""
    run_id = store.create_run("tiny-test", "Tiny")
    cameras = [a_camera(0.0, float(index), 0.0, 1.0) for index in range(frames)]
    for index, camera in enumerate(cameras):
        frame_id = index + 1
        store.record_frame(
            run_id, index=index, frame_id=frame_id, t_ns=index, jpeg=JPEG, overlay=[], camera=camera
        )
        store.record_event(
            run_id, "frame", {"index": index, "frame_id": frame_id, "camera": camera}
        )
        map_update = {
            "frame_id": frame_id,
            "points": [[0.0, 0.0, 1.0]],
            "point_colors": [[9, 9, 9]],
        }
        store.record_event(run_id, "map", map_update)
    return run_id


def a_recording_renderer() -> tuple[list[FollowCamera | None], CloudRenderer]:
    """A renderer that records which camera each view was drawn for."""
    drawn_for: list[FollowCamera | None] = []

    def render(
        points: NDArray[np.float32],
        colors: NDArray[np.uint8],
        bounds: Bounds,
        layer: SurfaceLayer,
        camera: FollowCamera | None,
    ) -> dict[str, str]:
        drawn_for.append(camera)
        return {"cloud_png": "png", "cloud_ids_png": "ids"}

    return drawn_for, render


def test_a_replay_draws_each_view_for_the_camera_of_the_frame_before_it(tmp_path: Path) -> None:
    # Given a recorded drive of three frames
    store = RunHistoryStore(tmp_path / "history.db")
    run_id = a_recorded_drive(store)
    drawn_for, render = a_recording_renderer()

    # When it replays with every map drawn (the clock runs fast)
    ticks = iter(range(0, 1000, 10))
    list(
        JournalPlayer(store, run_id, render_cloud=render, clock=lambda: float(next(ticks))).events()
    )

    # Then each view was drawn for the camera of its frame
    assert [camera and camera["z"] for camera in drawn_for] == [0.0, 1.0, 2.0]


def test_a_scrubbed_moment_is_drawn_for_its_own_camera(tmp_path: Path) -> None:
    with a_running_console(tmp_path, a_driving_map()) as base:
        play_to_the_end(base)
        with urllib.request.urlopen(f"{base}/runs", timeout=5) as response:
            run_id = json.loads(response.read())["runs"][0]["run_id"]
        with urllib.request.urlopen(f"{base}/runs/{run_id}/snapshot?seq=0", timeout=5) as response:
            snapshot = json.loads(response.read())
        follow_answer = post(f"{base}/control", {"action": "cloud_zoom", "factor": 1.0})[1]
    # The moment's own image, and a later redraw of it, are framed on its camera
    assert snapshot["camera"] is not None and snapshot["cloud"]["cloud_png"]
    assert follow_answer["camera"] == snapshot["camera"]


def test_the_page_has_a_follow_checkbox_checked_by_default(tmp_path: Path) -> None:
    with a_console_page(tmp_path) as page:
        assert '<input type="checkbox" id="cloud-follow" checked>' in page
        assert "action: 'cloud_follow'" in page
        assert "followBox.checked = pose.follow" in page
