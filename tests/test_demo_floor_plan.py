"""Live floor plan: every map point rendered into one stable image."""

from pathlib import Path

import numpy as np

from surmap.demo.server import DemoPlayer, FloorExtent, render_floor_plan
from surmap.slam.streaming import MapCloud
from surmap.types import Pose, Vec3
from tests.test_demo import FakeLiveBackend, _odom_with, _prepared_tiny, an_extent, floor_pixel

EXTENT = FloorExtent(min_x=0.0, max_x=10.0, min_z=0.0, max_z=10.0)


def points(*xz: tuple[float, float]) -> np.ndarray:
    return np.array(xz, dtype=np.float32).reshape(-1, 2)


def test_a_map_point_is_drawn_where_the_extent_puts_it_in_its_grey() -> None:
    # Given one point 3 m right and 7 m ahead, grey 200
    image = render_floor_plan(points((3.0, 7.0)), np.array([200], np.uint8), EXTENT)

    # When / Then its pixel carries that grey, opaque, and elsewhere is empty
    u, v = EXTENT.to_pixels(3.0, 7.0)
    red, green, blue, alpha = floor_pixel(image, u, v)
    assert (red, green, blue) == (200, 200, 200) and alpha > 0
    assert floor_pixel(image, *EXTENT.to_pixels(8.0, 1.0))[3] == 0


def test_denser_map_areas_are_drawn_more_opaque() -> None:
    # Given one point at one spot and twenty at another
    xz = points((2.0, 2.0), *[(8.0, 8.0)] * 20)
    image = render_floor_plan(xz, np.full(21, 128, np.uint8), EXTENT)

    # When / Then the dense spot is more opaque than the lone point
    assert (
        floor_pixel(image, *EXTENT.to_pixels(8.0, 8.0))[3]
        > floor_pixel(image, *EXTENT.to_pixels(2.0, 2.0))[3]
    )


def test_the_same_map_renders_the_same_image() -> None:
    # Given a map of many points
    rng = np.random.default_rng(7)
    xz = rng.uniform(0, 10, (50_000, 2)).astype(np.float32)
    grey = rng.integers(0, 255, 50_000).astype(np.uint8)

    # When / Then rendering it twice gives identical bytes (no resampling)
    assert render_floor_plan(xz, grey, EXTENT) == render_floor_plan(xz, grey, EXTENT)


def test_the_extent_maps_its_corners_to_the_padded_canvas() -> None:
    # Given / When / Then min corner bottom-left, max corner top-right
    assert EXTENT.to_pixels(0.0, 0.0) == (10.0, 330.0)
    assert EXTENT.to_pixels(10.0, 10.0) == (330.0, 10.0)


def test_the_map_extent_only_grows(tmp_path: Path) -> None:
    # Given a live map that first spans 20 m, then appears smaller
    fake = FakeLiveBackend(
        cloud=[((0.0, 0.0, 0.0), (90, 90, 90)), ((20.0, 0.0, 20.0), (90, 90, 90))]
    )
    player = DemoPlayer(_prepared_tiny(tmp_path), fps=1000.0, backend_factory=lambda: fake)
    extents = []
    for event in player.events():
        if event.kind == "map":
            extents.append(an_extent(event.data["extent"]))
            fake.cloud = MapCloud(np.zeros((1, 3), np.float32), np.full((1, 3), 90, np.uint8))

    # When / Then later map events keep the full extent, so the view never jumps
    assert len(extents) >= 1 and all(e.max_x >= 20.0 and e.max_z >= 20.0 for e in extents)


def test_the_camera_is_placed_on_the_map_not_on_raw_odometry(tmp_path: Path) -> None:
    # Given a frame whose odometry says origin but whose map-corrected pose
    # (after a loop closure) is 3 m right and 4 m ahead
    corrected = Pose(Vec3(3.0, 0.0, 4.0))
    fake = FakeLiveBackend(odometry={1: _odom_with(map_pose=corrected)})
    player = DemoPlayer(_prepared_tiny(tmp_path), fps=1000.0, backend_factory=lambda: fake)

    # When frame 1 is shown
    frame = next(event for event in player.events() if event.kind == "frame")

    # Then the camera sits where the map has it, on its trajectory
    camera = frame.data["camera"]
    assert isinstance(camera, dict) and (camera["x"], camera["z"]) == (3.0, 4.0)
