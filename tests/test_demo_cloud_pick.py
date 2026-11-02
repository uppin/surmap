"""Demo: hovering a surface in the 3D pane names it, selects it and brings its feed card up."""

import base64
import io
import json
import subprocess
import urllib.request
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.cloud_view import CloudViewer
from surmap.demo.history import RENDER_ONLY
from surmap.demo.view_math import VIEW_HELPERS
from tests.test_demo_cloud_ptz import play_to_the_end, post
from tests.test_demo_object_feed import NODE, a_console_page, needs_node
from tests.test_demo_regions import FakeRegionBackend
from tests.test_demo_surfaces import a_map_around_the_region, a_running_console, play

# A grey map, and two surfaces: 7 on the left of it, 9 on the right.
MAP = np.array(
    [[x, 0.0, z] for x in np.linspace(0, 4, 20) for z in np.linspace(0, 4, 20)], np.float32
)
GREY = np.full((len(MAP), 3), 120, np.uint8)
BOUNDS = (MAP.min(axis=0), MAP.max(axis=0))


def a_patch(x0: float, x1: float) -> NDArray[np.float32]:
    xs, zs = np.linspace(x0, x1, 15), np.linspace(1.5, 2.5, 15)
    return np.array([[x, -0.5, z] for x in xs for z in zs], np.float32)


LEFT, RIGHT = a_patch(0.5, 1.5), a_patch(2.5, 3.5)


def decode(png_b64: str) -> NDArray[np.uint8]:
    with Image.open(io.BytesIO(base64.b64decode(png_b64))) as image:
        rgba: NDArray[np.uint8] = np.array(image.convert("RGBA"))
    return rgba


def ids_of(png_b64: str) -> NDArray[np.int64]:
    """Each pixel's surface id (0 where no surface was drawn)."""
    rgba = decode(png_b64).astype(np.int64)
    ids: NDArray[np.int64] = np.where(rgba[..., 3] > 0, rgba[..., 0] + 256 * rgba[..., 1], 0)
    return ids


def test_the_id_image_holds_each_surfaces_id_on_the_pixels_it_drew() -> None:
    # Given a map with surfaces 7 and 9 over it
    viewer = CloudViewer()

    # When the view is drawn
    view = viewer.render_view(MAP, GREY, BOUNDS, ((7, LEFT, False), (9, RIGHT, False)))

    # Then the id image is the colour image's size, and names exactly the two surfaces
    ids = ids_of(view["cloud_ids_png"])
    assert ids.shape == decode(view["cloud_png"]).shape[:2]
    assert set(np.unique(ids).tolist()) == {0, 7, 9}
    # ... 7 left of 9, as they are in the map
    assert np.nonzero(ids == 7)[1].mean() < np.nonzero(ids == 9)[1].mean()


def test_an_id_above_255_survives_the_encoding() -> None:
    view = CloudViewer().render_view(MAP, GREY, BOUNDS, ((300, LEFT, False),))
    assert set(np.unique(ids_of(view["cloud_ids_png"])).tolist()) == {0, 300}


def test_map_points_alone_have_no_id() -> None:
    view = CloudViewer().render_view(MAP, GREY, BOUNDS, ())
    assert not ids_of(view["cloud_ids_png"]).any()


def test_hidden_surfaces_cannot_be_picked() -> None:
    # Given surfaces hidden by the viewer
    viewer = CloudViewer()
    viewer.set_surfaces_visible(False)

    # When the view is drawn
    view = viewer.render_view(MAP, GREY, BOUNDS, ((7, LEFT, False),))

    # Then nothing in it can be picked
    assert not ids_of(view["cloud_ids_png"]).any()


def test_a_moving_surface_owns_the_pixels_it_is_drawn_over() -> None:
    # Given a moving surface 9 lying exactly over a static surface 7
    view = CloudViewer().render_view(MAP, GREY, BOUNDS, ((9, LEFT, True), (7, LEFT, False)))

    # Then the pixels pick 9, the surface drawn on top
    assert set(np.unique(ids_of(view["cloud_ids_png"])).tolist()) == {0, 9}


def test_the_id_image_is_never_journalled() -> None:
    assert "cloud_ids_png" in RENDER_ONLY


def test_live_map_updates_carry_the_id_image(tmp_path: Path) -> None:
    # When a live run with a car's surface plays
    events = play(tmp_path, a_map_around_the_region())

    # Then its map and final views can be picked
    views = [event for event in events if event.kind in ("map", "final")]
    assert views and all("cloud_ids_png" in event.data for event in views)
    final = views[-1].data["cloud_ids_png"]
    assert isinstance(final, str) and 1 in ids_of(final)


def test_moving_the_view_answers_with_its_id_image_too(tmp_path: Path) -> None:
    with a_running_console(tmp_path, a_map_around_the_region(FakeRegionBackend())) as base:
        play_to_the_end(base)
        answer = post(f"{base}/control", {"action": "cloud_orbit", "d_azimuth": 0.2})[1]
    picked = answer["cloud_ids_png"]
    assert isinstance(picked, str) and 1 in ids_of(picked)


def test_a_scrubbed_moment_can_be_picked(tmp_path: Path) -> None:
    with a_running_console(tmp_path, a_map_around_the_region()) as base:
        play_to_the_end(base)
        with urllib.request.urlopen(f"{base}/runs", timeout=5) as response:
            run_id = json.loads(response.read())["runs"][0]["run_id"]
        with urllib.request.urlopen(f"{base}/runs/{run_id}/snapshot?seq=1", timeout=5) as response:
            cloud = json.loads(response.read())["cloud"]
    assert 1 in ids_of(cloud["cloud_ids_png"])


def run_view_helpers(expression: str) -> object:
    assert NODE is not None
    script = VIEW_HELPERS.format() + f"\nconsole.log(JSON.stringify({expression}));\n"
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


# A 6 x 4 id image (RGBA, row-major): surface 300 at (1, 1), surface 5 at (4, 2).
IDS_JS = """(() => {
  const data = new Uint8ClampedArray(6 * 4 * 4);
  const put = (x, y, id) => { const i = (y * 6 + x) * 4;
    data[i] = id & 255; data[i + 1] = id >> 8; data[i + 3] = 255; };
  put(1, 1, 300); put(4, 2, 5);
  return data;
})()"""


@needs_node
def test_hover_picks_the_surface_pixel_nearest_the_cursor() -> None:
    picks = run_view_helpers(
        f"(() => {{ const ids = {IDS_JS}; return ["
        "surfaceIdNear(ids, 6, 4, 1, 1, 2), surfaceIdNear(ids, 6, 4, 2, 1, 2),"
        "surfaceIdNear(ids, 6, 4, 4, 3, 2), surfaceIdNear(ids, 6, 4, 3, 2, 1)]; })()"
    )
    # On 300, beside it, below 5, and between both but nearer 5
    assert picks == [300, 300, 5, 5]


@needs_node
def test_hover_far_from_every_surface_picks_nothing() -> None:
    assert run_view_helpers(f"surfaceIdNear({IDS_JS}, 6, 4, 0, 3, 1)") == 0


@needs_node
def test_the_selection_covers_every_pixel_of_the_hovered_surface_only() -> None:
    selected = run_view_helpers(
        f"(() => {{ const mask = selectionMask({IDS_JS}, 300);"
        " const on = []; for (let i = 0; i < mask.length; i += 4) if (mask[i + 3]) on.push(i / 4);"
        " return on; }})()"
    )
    assert selected == [1 * 6 + 1]


def test_the_page_wires_hover_to_the_tooltip_the_selection_and_the_feed(tmp_path: Path) -> None:
    with a_console_page(tmp_path) as page:
        assert 'id="cloud-tip"' in page
        assert "surfaceIdNear(" in page and "selectionMask(" in page
        assert "focusFeedItem(" in page
        assert "cloud_ids_png" in page
