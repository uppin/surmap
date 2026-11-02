"""Demo: the 3D pane's pan, tilt and zoom answer at any time, run or no run."""

import json
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from surmap.demo.cloud_view import CloudPose, CloudViewer
from surmap.demo.server import PlaybackControls
from tests.test_demo_regions import FakeRegionBackend
from tests.test_demo_surfaces import a_map_around_the_region, a_running_console

START = CloudPose().azimuth  # the view's default azimuth
CORNERS = np.array([[0.0, 1.0, 2.0], [2.5, 3.0, 4.0], [1.0, 1.5, 3.5]], np.float32)
GREY = np.full((3, 3), 120, np.uint8)
BOUNDS = (CORNERS.min(axis=0), CORNERS.max(axis=0))


def post(url: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status), json.loads(response.read())
    except urllib.error.HTTPError as error:
        return int(error.code), {}


def play_to_the_end(base: str) -> None:
    with urllib.request.urlopen(f"{base}/stream", timeout=30) as response:
        response.read()


def test_a_viewer_draws_nothing_again_before_it_has_drawn_a_scene() -> None:
    assert CloudViewer().rerender() is None


def test_moving_the_view_redraws_the_last_scene_from_the_new_pose() -> None:
    # Given a viewer that drew a cloud
    viewer = CloudViewer()
    first = viewer.render(CORNERS, GREY, BOUNDS, ())

    # When it orbits, then is reset
    viewer.orbit(0.8, 0.3)
    orbited = viewer.rerender()
    viewer.reset()

    # Then the same scene is drawn from the orbited pose, and back again
    assert orbited is not None and orbited != first
    assert viewer.rerender() == first


def test_every_runs_controls_share_the_sessions_view() -> None:
    # Given two runs' controls over one viewer
    viewer = CloudViewer()
    first_run, second_run = PlaybackControls(viewer), PlaybackControls(viewer)

    # When the first run's view is orbited
    first_run.cloud_orbit(0.5, 0.0)

    # Then the second run sees the same pose
    assert second_run.cloud_pose().azimuth == START + 0.5


def test_the_3d_pane_moves_after_the_run_has_finished(tmp_path: Path) -> None:
    # Given a console whose run played to the end
    with a_running_console(tmp_path, a_map_around_the_region(FakeRegionBackend())) as base:
        play_to_the_end(base)

        # When the viewer drags the 3D pane
        status, answer = post(f"{base}/control", {"action": "cloud_orbit", "d_azimuth": 0.4})

        # Then it is accepted and answered with the cloud drawn from the new pose
        assert status == 200
        assert answer["azimuth"] == START + 0.4
        assert isinstance(answer["cloud_png"], str) and answer["cloud_png"]


def test_zoom_and_pan_answer_with_a_new_image_too(tmp_path: Path) -> None:
    with a_running_console(tmp_path, a_map_around_the_region(FakeRegionBackend())) as base:
        play_to_the_end(base)

        zoomed = post(f"{base}/control", {"action": "cloud_zoom", "factor": 0.5})[1]
        panned = post(f"{base}/control", {"action": "cloud_pan", "dx": 0.5, "dz": 0.0})[1]

        assert zoomed["cloud_png"] and panned["cloud_png"]
        assert zoomed["cloud_png"] != panned["cloud_png"]


def test_before_anything_was_drawn_the_pose_still_moves(tmp_path: Path) -> None:
    # Given a console that has played nothing yet
    with a_running_console(tmp_path, a_map_around_the_region(FakeRegionBackend())) as base:
        # When the viewer orbits
        status, answer = post(f"{base}/control", {"action": "cloud_orbit", "d_azimuth": 0.3})

        # Then the pose moves, with no image to show yet
        assert (status, answer["azimuth"], answer["cloud_png"]) == (200, START + 0.3, None)


def test_the_view_carries_into_the_next_run(tmp_path: Path) -> None:
    # Given a view orbited before a run
    with a_running_console(tmp_path, a_map_around_the_region(FakeRegionBackend())) as base:
        post(f"{base}/control", {"action": "cloud_orbit", "d_azimuth": 0.5})

        # When a run plays and the view is orbited again
        play_to_the_end(base)
        answer = post(f"{base}/control", {"action": "cloud_orbit", "d_azimuth": 0.25})[1]

        # Then the two orbits add up: the run did not reset the view
        assert answer["azimuth"] == START + 0.5 + 0.25


def test_pause_still_needs_a_run(tmp_path: Path) -> None:
    with a_running_console(tmp_path, a_map_around_the_region(FakeRegionBackend())) as base:
        assert post(f"{base}/control", {"action": "pause"})[0] == 409
