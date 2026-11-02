"""Demo: the video's point overlay can be switched off, and a frame's dense depth on."""

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

from surmap.demo.dense_view import dense_depth_png
from surmap.demo.server import DEPTH_COLOURS, make_demo_server
from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from tests.test_demo import _prepared_tiny
from tests.test_demo_object_feed import a_console_page

STOPS = (1.0, 3.0, 6.0)
NEAR, MID, FAR = DEPTH_COLOURS


def rgba(png: bytes) -> NDArray[np.uint8]:
    with Image.open(io.BytesIO(png)) as image:
        assert image.mode == "RGBA"
        decoded: NDArray[np.uint8] = np.asarray(image)
    return decoded


def a_textured_pair(shift_px: int) -> tuple[FrameImage, FrameImage]:
    """A 160x120 noise image and its copy shifted left by `shift_px`: one flat wall."""
    texture = np.random.default_rng(7).integers(0, 255, (120, 160 + shift_px), dtype=np.uint8)
    left, right = texture[:, shift_px:], texture[:, :160]
    return a_frame(left), a_frame(right)


def a_frame(grey: NDArray[np.uint8]) -> FrameImage:
    rgb = np.repeat(grey[:, :, None], 3, axis=2)
    return FrameImage(grey.shape[1], grey.shape[0], "raw_rgb", rgb.tobytes())


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


def test_the_stereo_depth_map_puts_a_flat_wall_at_its_disparitys_depth() -> None:
    # Given a rig and a pair whose views of one wall differ by 8 px
    rig = StereoRig(fx=200.0, fy=200.0, cx=80.0, cy=60.0, baseline_m=0.1)
    left, right = a_textured_pair(shift_px=8)

    # When its dense depth is matched
    depth = StereoReconstructor().depth_map(left, right, rig)

    # Then the wall's interior sits at fx * b / d = 2.5 m
    assert depth.shape == (120, 160)
    assert float(np.median(depth[20:100, 30:130])) == pytest.approx(2.5, rel=0.02)


def test_the_server_serves_a_frames_dense_depth_at_the_display_size(tmp_path: Path) -> None:
    # Given a demo server for the tiny scene (frames at t_ns 100 and 200)
    with a_demo_server(tmp_path) as base:
        # When the page asks for the dense depth of the frame at t_ns 100
        with urllib.request.urlopen(f"{base}/dense-depth?t_ns=100", timeout=10) as response:
            content_type = response.headers["Content-Type"]
            image = rgba(response.read())

    # Then it gets a PNG the size of the displayed frame
    assert content_type == "image/png"
    assert image.shape == (240, 376, 4)


def test_the_server_has_no_dense_depth_for_a_frame_the_scene_does_not_have(
    tmp_path: Path,
) -> None:
    # Given a demo server for the tiny scene
    with a_demo_server(tmp_path) as base:
        # When the page asks for a frame the scene has no pair for
        with pytest.raises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(f"{base}/dense-depth?t_ns=150", timeout=10)

    # Then it is told there is none
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
        # ... dense depth is fetched for the shown frame, and either box redraws it
        assert "'/dense-depth?dataset='" in page
        assert "showPoints.addEventListener('change', redrawView)" in page
        assert "showDense.addEventListener('change', redrawView)" in page
