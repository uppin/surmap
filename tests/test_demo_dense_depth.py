"""Demo: the video's point overlay can be switched off, and RTAB-Map's dense depth of a frame on."""

import io
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.datasets import DISPLAY_HEIGHT, DISPLAY_WIDTH
from surmap.demo.dense_view import dense_depth_png
from surmap.demo.server import DEPTH_COLOURS, make_demo_server
from tests.test_demo import _prepared_tiny
from tests.test_demo_object_feed import a_console_page
from tests.test_demo_replay import Console, a_console, a_recorded_run, kinds, sse_events

STOPS = (1.0, 3.0, 6.0)
NEAR, MID, FAR = DEPTH_COLOURS


def rgba(png: bytes) -> NDArray[np.uint8]:
    with Image.open(io.BytesIO(png)) as image:
        assert image.mode == "RGBA"
        decoded: NDArray[np.uint8] = np.asarray(image)
    return decoded


@contextmanager
def a_demo_server(tmp_path: Path) -> Iterator[str]:
    server = make_demo_server(
        _prepared_tiny(tmp_path), host="127.0.0.1", port=0, with_rtabmap=False
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dense_depth_paints_each_pixel_in_the_overlay_ramp_colour_of_its_depth() -> None:
    # Given a depth image: near, mid and far pixels, and one with no match (0)
    depth = np.array([[0.5, 3.0], [9.0, 0.0]], np.float32)

    # When it is rendered at its own size
    image = rgba(dense_depth_png(depth, (2, 2), STOPS, DEPTH_COLOURS))

    # Then each matched pixel has its depth's ramp colour, opaque
    assert tuple(image[0, 0]) == (*NEAR, 255)
    assert tuple(image[0, 1]) == (*MID, 255)
    assert tuple(image[1, 0]) == (*FAR, 255)
    # ... and the unmatched one is transparent, so the frame shows through
    assert image[1, 1, 3] == 0


def test_dense_depth_is_stretched_to_the_frames_display_size() -> None:
    # Given a depth image at the matching resolution, half the frame's
    depth = np.full((120, 188), 2.0, np.float32)

    # When it is rendered for a 376x240 frame
    image = rgba(dense_depth_png(depth, (376, 240), STOPS, DEPTH_COLOURS))

    # Then it covers the whole frame
    assert image.shape == (240, 376, 4)


def ramp_colour(depth_m: float, stops: tuple[float, float, float]) -> tuple[int, ...]:
    """The overlay colour of one depth, as the dense depth image paints it."""
    return tuple(
        rgba(dense_depth_png(np.full((1, 1), depth_m, np.float32), (1, 1), stops, DEPTH_COLOURS))[
            0, 0
        ]
    )


def png_of(console: Console, path: str) -> NDArray[np.uint8]:
    with urllib.request.urlopen(f"{console.base}{path}", timeout=20) as response:
        assert response.headers["Content-Type"] == "image/png"
        return rgba(response.read())


def test_a_frames_dense_depth_is_rtabmaps_journalled_disparity(tmp_path: Path) -> None:
    # Given a run whose RTAB-Map sidecar journalled a wall 2 m away for each SAM frame
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)

        # When the page asks for the dense depth of the run's first frame
        image = png_of(console, f"/runs/{run_id}/dense-depth?frame_id=1")

    # Then the whole displayed frame is painted the overlay colour of 2 m
    assert image.shape == (DISPLAY_HEIGHT, DISPLAY_WIDTH, 4)
    wall = ramp_colour(2.0, STOPS)  # the tiny scene keeps the default stops
    assert {tuple(pixel) for pixel in image.reshape(-1, 4)} == {wall}


def test_a_replays_dense_depth_is_its_recordings_journalled_disparity(tmp_path: Path) -> None:
    # Given a replay of a run recorded with RTAB-Map
    with a_console(tmp_path) as console:
        recorded = a_recorded_run(console)
        replay = str(kinds(console.stream(f"?replay={recorded}&speed=0"), "run")[0]["run_id"])

        # When the page asks for the replay's dense depth of a frame
        image = png_of(console, f"/runs/{replay}/dense-depth?frame_id=2")

    # Then it is the recording's: the wall, over the whole frame
    assert image.shape == (DISPLAY_HEIGHT, DISPLAY_WIDTH, 4)
    assert (image[..., 3] == 255).all()


def test_there_is_no_dense_depth_for_a_frame_rtabmap_did_not_journal(tmp_path: Path) -> None:
    # Given a recorded run whose sidecar journalled frames 1 and 2
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)

        # When the page asks for a frame it has no dense buffer for, or a run that does not exist
        missing_frame = console.status_of(f"/runs/{run_id}/dense-depth?frame_id=3")
        missing_run = console.status_of("/runs/nope/dense-depth?frame_id=1")

    # Then there is none: nothing is matched in its place
    assert (missing_frame, missing_run) == (404, 404)


def test_without_rtabmap_no_frame_has_dense_depth(tmp_path: Path) -> None:
    # Given a run played without RTAB-Map
    with a_demo_server(tmp_path) as base:
        with urllib.request.urlopen(f"{base}/stream", timeout=10) as response:
            run_id = kinds(sse_events(response.read().decode()), "run")[0]["run_id"]

        # When the page asks for a frame's dense depth
        with pytest.raises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(f"{base}/runs/{run_id}/dense-depth?frame_id=1", timeout=10)

    # Then there is none
    assert raised.value.code == 404


def test_the_page_shows_rtab_points_by_default_and_dense_depth_on_request(
    tmp_path: Path,
) -> None:
    # When the console page is served
    with a_console_page(tmp_path) as page:
        # Then the video has a checked points toggle and an unchecked dense depth one
        assert '<input type="checkbox" id="show-points" checked>' in page
        assert '<input type="checkbox" id="show-dense">' in page
        # ... the points are drawn only while their box is checked
        assert "if (showPoints.checked)" in page
        # ... RTAB-Map's dense depth is fetched for the shown frame of the run, by frame id
        assert "'/runs/' + encodeURIComponent(currentRunId) + '/dense-depth?frame_id='" in page
        # ... either box redraws it
        assert "showPoints.addEventListener('change', redrawView)" in page
        assert "showDense.addEventListener('change', redrawView)" in page


def test_the_page_says_when_rtabmap_has_no_dense_depth_for_the_frame(tmp_path: Path) -> None:
    # When the console page is served
    with a_console_page(tmp_path) as page:
        # Then a missing frame is named as RTAB-Map's, and the region that brings it retries
        assert "No RTAB-Map dense depth for this frame" in page
        assert "retryDense(data.frame_id)" in page


def test_the_page_draws_a_frame_together_with_its_dense_depth(tmp_path: Path) -> None:
    # When the console page is served
    with a_console_page(tmp_path) as page:
        # Then with dense depth on, a frame waits on screen for its overlay instead of
        # flashing without it
        assert (
            "if (!dense && !denseMissing.has(denseKey(frameId))) { loadDense(frameId); return; }"
            in page
        )
        # ... and a frame RTAB-Map has none for is remembered, drawn plain, not asked again
        assert "denseMissing.add(key)" in page
