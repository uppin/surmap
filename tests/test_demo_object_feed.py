"""Demo: the object feed, and each SAM mask's own dense points on the SAM pane."""

import json
import shutil
import subprocess
import threading
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
from surmap.demo.view_math import VIEW_HELPERS

from surmap.demo.events import RegionPlacer, SurfaceAssigner
from surmap.demo.server import DemoEvent, make_demo_server
from surmap.slam.dense import DenseBufferRegionSource, RegionRig
from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus
from surmap.types import Pose, Vec3
from tests.test_demo import _prepared_tiny
from tests.test_slam_dense import a_dense_frame, a_rig, a_wall

DISPLAY = (200, 160)  # twice the test rig's 100 x 80
SQUARE_ON_DISPLAY = [[40.0, 40.0], [80.0, 40.0], [80.0, 80.0], [40.0, 80.0]]
CAMERA = Pose(Vec3(1.0, 2.0, 3.0))


def a_sam_event(frame_id: int = 7, polygon: list[list[float]] | None = None) -> DemoEvent:
    mask = polygon if polygon is not None else SQUARE_ON_DISPLAY
    return DemoEvent(
        "sam",
        {
            "frame_id": frame_id,
            "objects": [{"track_id": 4, "label": "car", "mask_polygon": mask}],
        },
    )


def a_journalled_frame() -> DenseBufferRegionSource:
    """Frame 7: a wall 2 m in front of a camera placed at (1, 2, 3)."""
    return DenseBufferRegionSource(a_rig(), [a_dense_frame(a_wall(2.5), to_map=CAMERA)])


def only_region(event: DemoEvent) -> dict[str, object]:
    regions = event.data["regions"]
    assert isinstance(regions, list) and len(regions) == 1
    region = regions[0]
    assert isinstance(region, dict)
    return region


def test_a_region_names_the_camera_that_saw_it(tmp_path: Path) -> None:
    # Given a replay's dense buffer for frame 7
    placer = RegionPlacer(a_journalled_frame(), DISPLAY)

    # When SAM's car mask on frame 7 is placed
    region = only_region(placer.region_event(a_sam_event()))

    # Then the region carries the camera position its points were placed from
    assert region["viewpoint"] == [1.0, 2.0, 3.0]


def test_a_region_carries_its_points_pixels_on_the_sam_image_with_their_range() -> None:
    # Given a replay's dense buffer for frame 7
    placer = RegionPlacer(a_journalled_frame(), DISPLAY)

    # When SAM's car mask on frame 7 is placed
    region = only_region(placer.region_event(a_sam_event()))

    # Then every point has its display pixel on the mask and its range from the camera
    pixels = np.array(region["pixels"], np.float64)
    assert pixels.shape == (21 * 21, 3)
    np.testing.assert_allclose(pixels[:, :2].min(axis=0), [40.0, 40.0], atol=1e-3)
    np.testing.assert_allclose(pixels[:, :2].max(axis=0), [80.0, 80.0], atol=1e-3)
    assert float(pixels[:, 2].min()) == pytest.approx(2.0, abs=1e-3)
    assert float(pixels[:, 2].max()) < 2.3


def test_region_pixels_are_sampled_to_at_most_1500() -> None:
    # Given a mask over the whole display image
    whole = [[0.0, 0.0], [199.0, 0.0], [199.0, 159.0], [0.0, 159.0]]
    placer = RegionPlacer(a_journalled_frame(), DISPLAY)

    # When it is placed
    region = only_region(placer.region_event(a_sam_event(polygon=whole)))

    # Then its pixels are capped, while its points are not cut to them
    pixels, points = region["pixels"], region["points"]
    assert isinstance(pixels, list) and isinstance(points, list)
    assert len(pixels) == 1500
    assert len(points) > 1500


class BackgroundCatchingSource:
    """A source whose mask caught 100 car points 5 m away and 30 background points 12 m away."""

    region_rig: RegionRig | None = a_rig()

    def region_points(self, query: RegionQuery, timeout: float = 5.0) -> RegionResult:
        car = [Vec3(0.03 * i, 0.0, 5.0) for i in range(100)]
        background = [Vec3(0.03 * i, 0.0, 12.0) for i in range(30)]
        return RegionResult(
            query.query_id,
            query.frame_id,
            query.channel,
            RegionStatus.OK,
            tuple(car + background),
            Pose(Vec3(0.0, 0.0, 0.0)),
        )


def test_the_sam_pane_gets_only_the_objects_own_points() -> None:
    # Given a mask that also caught background far behind the car
    placer = RegionPlacer(BackgroundCatchingSource(), DISPLAY)

    # When it is placed
    region = only_region(placer.region_event(a_sam_event()))

    # Then the pixels drawn on the SAM pane are the car's, all 5 m away
    ranges = np.array(region["pixels"], np.float64)[:, 2]
    assert len(ranges) == 100
    np.testing.assert_allclose(ranges, np.hypot(5.0, 0.03 * np.arange(100)), atol=1e-3)


def test_the_surface_is_built_from_the_band_seen_from_the_regions_camera() -> None:
    # Given that region placed
    region = RegionPlacer(BackgroundCatchingSource(), DISPLAY).region_event(a_sam_event())

    # When it is assigned to a surface
    surface = SurfaceAssigner().surface_event(region)

    # Then the surface holds the car only
    assert surface is not None
    surfaces = surface.data["surfaces"]
    assert isinstance(surfaces, list)
    assert [s["total_points"] for s in surfaces] == [100]
    depth = np.array(surfaces[0]["points"], np.float64)[:, 2]
    assert float(depth.max()) == pytest.approx(5.0)


def test_a_source_without_a_rig_gives_regions_no_pixels() -> None:
    # Given a source that does not know how it answers (no rig)
    source = BackgroundCatchingSource()
    source.region_rig = None

    # When a mask is placed
    region = only_region(RegionPlacer(source, DISPLAY).region_event(a_sam_event()))

    # Then there are no pixels to draw, but the camera is still named
    assert region["pixels"] == []
    assert region["viewpoint"] == [0.0, 0.0, 0.0]


@contextmanager
def a_console_page(tmp_path: Path) -> Iterator[str]:
    server = make_demo_server(
        _prepared_tiny(tmp_path), host="127.0.0.1", port=0, with_rtabmap=False, sam_fake=True
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = str(server.server_address[0]), int(server.server_address[1])
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
            yield response.read().decode()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_page_has_an_object_feed_fed_by_surfaces_and_snapshots(tmp_path: Path) -> None:
    # When the console page is served
    with a_console_page(tmp_path) as page:
        # Then it has the feed, filled by surface events and by a scrubbed moment's surfaces
        assert 'id="object-feed"' in page
        assert "source.addEventListener('surface'" in page
        assert "feedSurfaceEvent(" in page
        assert "feedSnapshot(snap.surfaces" in page
        # ... and cleared when a new run starts
        assert "clearFeed()" in page


def test_the_sam_pane_draws_each_regions_points_by_depth(tmp_path: Path) -> None:
    # When the console page is served
    with a_console_page(tmp_path) as page:
        # Then region events are kept for the SAM pane, which draws them over its masks
        assert "source.addEventListener('region'" in page
        assert "noteRegions(" in page
        assert "drawSamDepth(" in page


NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_view_helpers(expression: str) -> object:
    """Evaluate `expression` after the page's view helpers, in node; its JSON value."""
    assert NODE is not None
    script = VIEW_HELPERS.format() + f"\nconsole.log(JSON.stringify({expression}));\n"
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@needs_node
def test_a_drag_sends_its_whole_movement_while_a_post_is_pending() -> None:
    # Given three pointer moves of one drag, merged while a post was in flight
    merged = run_view_helpers(
        "[{action: 'cloud_orbit', d_azimuth: 0.1, d_elevation: 0.02},"
        " {action: 'cloud_orbit', d_azimuth: 0.2, d_elevation: -0.01},"
        " {action: 'cloud_orbit', d_azimuth: 0.3, d_elevation: 0.04}]"
        ".reduce((pending, body) => mergeCloudBody(pending, body), null)"
    )

    # Then the post carries the sum of all three
    assert isinstance(merged, dict)
    assert merged["action"] == "cloud_orbit"
    assert merged["d_azimuth"] == pytest.approx(0.6)
    assert merged["d_elevation"] == pytest.approx(0.05)


@needs_node
def test_merged_zooms_multiply_and_pans_add() -> None:
    zoom = run_view_helpers(
        "mergeCloudBody({action: 'cloud_zoom', factor: 0.5}, {action: 'cloud_zoom', factor: 0.5})"
    )
    pan = run_view_helpers(
        "mergeCloudBody({action: 'cloud_pan', dx: 1, dz: 2}, {action: 'cloud_pan', dx: 3, dz: 4})"
    )
    assert zoom == {"action": "cloud_zoom", "factor": 0.25}
    assert pan == {"action": "cloud_pan", "dx": 4, "dz": 6}


@needs_node
def test_a_different_action_replaces_the_pending_one() -> None:
    merged = run_view_helpers(
        "mergeCloudBody({action: 'cloud_pan', dx: 1, dz: 2}, {action: 'cloud_zoom', factor: 2})"
    )
    assert merged == {"action": "cloud_zoom", "factor": 2}


@needs_node
def test_depth_colours_run_from_near_to_far_over_the_objects_own_range() -> None:
    # When the nearest, middle and farthest of an object's points are coloured
    colours = run_view_helpers("[0, 0.5, 1].map((t) => depthColour(t))")
    assert isinstance(colours, list)
    near, middle, far = colours

    # Then near is warm, far is cool, and they differ from the middle
    assert near[0] > near[2] and far[2] > far[0]
    assert near != middle != far


@needs_node
def test_a_preview_centres_the_object_and_fits_it_in_its_canvas() -> None:
    # Given an object 2 m wide, viewed from straight ahead at zoom 1
    projected = run_view_helpers(
        "orbitProject([[9, 0, 20], [11, 0, 20], [10, 1, 20]],"
        " {azimuth: 0, elevation: 0, zoom: 1, panX: 0, panY: 0}, 200, 100)"
    )

    # Then every point lands inside the canvas, centred on it
    assert isinstance(projected, list) and len(projected) == 3
    xs = [p[0] for p in projected]
    ys = [p[1] for p in projected]
    assert all(0 <= x <= 200 for x in xs) and all(0 <= y <= 100 for y in ys)
    assert (min(xs) + max(xs)) / 2 == pytest.approx(100, abs=1)


@needs_node
def test_orbiting_a_preview_turns_the_object() -> None:
    # Given the same object seen at azimuth 0 and a quarter turn round
    views = run_view_helpers(
        "[0, Math.PI / 2].map((azimuth) => orbitProject([[9, 0, 20], [11, 0, 20]],"
        " {azimuth, elevation: 0, zoom: 1, panX: 0, panY: 0}, 200, 100))"
    )
    assert isinstance(views, list)
    ahead, turned = views

    # Then the width it showed head-on collapses edge-on
    assert abs(ahead[0][0] - ahead[1][0]) > 50
    assert abs(turned[0][0] - turned[1][0]) < 1


@needs_node
def test_the_rendered_page_script_parses(tmp_path: Path) -> None:
    # Given the served page's script
    with a_console_page(tmp_path) as page:
        script = page.split("<script>", 1)[1].split("</script>", 1)[0]
    path = tmp_path / "page.js"
    path.write_text(script)

    # Then node accepts it
    assert NODE is not None
    checked = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
