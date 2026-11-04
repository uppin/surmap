"""The chat's live drone map: the map the flying drone builds, drawn with the demo 3D pane's
Follow view, from the renderer up to `GET /sim/map/<scenario>` on the real agent server."""

from __future__ import annotations

import asyncio
import base64
import http.client
import io
import json
import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.cloud_view import CAMERA_MARKER, CLOUD_VIEW_PX, follow_camera, render_follow_view
from surmap.types import Pose, Vec3
from tests.fleet_fakes import drone_frame
from tests.fleet_perception_fakes import (
    NE_D1,
    SW_D1,
    a_perception,
    an_open_perception,
    blocks,
)
from tests.fleet_tool_fakes import SCENARIO, FleetStation, a_fleet_station

RED = (230, 40, 40)
WIDTH, HEIGHT = CLOUD_VIEW_PX


def yawed(degrees: float) -> Pose:
    """A camera at the origin turned `degrees` about the map's (down-pointing) y axis."""
    half = math.radians(degrees) / 2
    return Pose(Vec3(0.0, 0.0, 0.0), (0.0, math.sin(half), 0.0, math.cos(half)))


def a_wall_ahead(
    z: float, colour: tuple[int, int, int] = RED
) -> tuple[NDArray[np.float32], NDArray[np.uint8]]:
    """A patch of points `z` metres along the map's +z, at the camera's height."""
    xs, ys = np.meshgrid(np.linspace(-2.0, 2.0, 40), np.linspace(-1.0, 1.0, 20))
    points = np.stack([xs.ravel(), ys.ravel(), np.full(xs.size, z)], axis=1).astype(np.float32)
    return points, np.tile(np.array(colour, dtype=np.uint8), (len(points), 1))


def pixels_of(png: str) -> NDArray[np.uint8]:
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(png))).convert("RGB"))


def where(image: NDArray[np.uint8], colour: tuple[int, int, int]) -> tuple[float, float]:
    """The mean (column, row) of the pixels of exactly `colour`."""
    rows, columns = np.nonzero(np.all(image == np.array(colour, dtype=np.uint8), axis=2))
    assert len(rows), f"no {colour} pixel drawn"
    return float(columns.mean()), float(rows.mean())


# ---- the follow camera -----------------------------------------------------------------------


def test_a_camera_looking_along_the_map_z_heads_along_z() -> None:
    # When the follow camera of an unturned camera at (3, 1, 5) is taken
    camera = follow_camera(Pose(Vec3(3.0, 1.0, 5.0), (0.0, 0.0, 0.0, 1.0)))

    # Then it sits at x 3, z 5 on the floor, heading along +z
    assert camera == {"x": 3.0, "z": 5.0, "dx": 0.0, "dz": 1.0}


def test_a_turned_camera_heads_where_its_optical_axis_points() -> None:
    # When the follow camera of a camera turned 90° about y is taken
    camera = follow_camera(yawed(90.0))

    # Then it heads along +x
    assert (round(camera["dx"], 6), round(camera["dz"], 6)) == (1.0, 0.0)


# ---- the follow view -------------------------------------------------------------------------


def test_the_follow_view_puts_the_drone_three_quarters_down_the_middle() -> None:
    # Given a map with nothing but a wall ahead of a drone at the origin heading along +z
    points, colours = a_wall_ahead(12.0)

    # When the map is drawn in the follow view of that drone
    image = pixels_of(render_follow_view(points, colours, follow_camera(yawed(0.0))))

    # Then the drone's yellow arrow is centred, three quarters down the image
    column, row = where(image, CAMERA_MARKER)
    assert (round(column / WIDTH, 2), abs(row / HEIGHT - 0.75) < 0.05) == (0.5, True)


def test_the_follow_view_shows_what_lies_ahead_of_the_drone_above_it() -> None:
    # Given a wall 12 m ahead of a drone heading along +z
    points, colours = a_wall_ahead(12.0)

    # When the map is drawn in the follow view of that drone
    image = pixels_of(render_follow_view(points, colours, follow_camera(yawed(0.0))))

    # Then the wall is drawn above the drone's arrow, in the middle of the view
    wall_column, wall_row = where(image, RED)
    _, arrow_row = where(image, CAMERA_MARKER)
    assert (round(wall_column / WIDTH, 1), wall_row < arrow_row) == (0.5, True)


def test_the_follow_view_turns_with_the_drone() -> None:
    # Given a wall along +z, and a drone turned to head along +x
    points, colours = a_wall_ahead(12.0)

    # When the map is drawn in the follow view of that drone
    image = pixels_of(render_follow_view(points, colours, follow_camera(yawed(90.0))))

    # Then the wall, now on the drone's left, is drawn left of the middle
    wall_column, _ = where(image, RED)
    assert wall_column < WIDTH / 2


def test_an_empty_map_is_still_drawn_with_its_drone() -> None:
    # When an empty map is drawn in the follow view of a drone
    image = pixels_of(
        render_follow_view(
            np.zeros((0, 3), np.float32), np.zeros((0, 3), np.uint8), follow_camera(yawed(0.0))
        )
    )

    # Then the image shows the drone's arrow alone
    assert image.shape[:2] == (HEIGHT, WIDTH) and where(image, CAMERA_MARKER)


# ---- the drone map of a page connection ------------------------------------------------------


def test_a_connection_with_no_frames_has_no_drone_map() -> None:
    # Given a page that has only said hello
    page = an_open_perception()

    # Then it has no drone map
    assert page.perception.drone_map() is None


def test_the_drone_map_is_the_map_of_the_drone_streamed_now() -> None:
    # Given a page that streamed nest-sw-d1's frames, then nest-ne-d1's
    page = an_open_perception()
    page.streams(*blocks((SW_D1, 3), (NE_D1, 2)))

    # When its drone map is taken
    found = page.perception.drone_map()

    # Then it is nest-ne-d1's map, at its last odometry pose
    assert found is not None
    assert (found.drone_id, len(found.cloud.points), found.pose) == (
        NE_D1,
        2,
        page.backends.of_frame(5).last_pose,
    )


def test_a_drone_map_before_any_pose_has_none() -> None:
    # Given a page whose drone's map has answered no odometry yet
    page = a_perception(posing=False).opened()
    page.streams(*blocks((SW_D1, 1)))

    # When its drone map is taken
    found = page.perception.drone_map()

    # Then it is nest-sw-d1's map, without a pose
    assert found is not None and (found.drone_id, found.pose) == (SW_D1, None)


# ---- GET /sim/map/<scenario> -----------------------------------------------------------------


async def get_map(station: FleetStation, scenario: str = SCENARIO) -> tuple[int, bytes, str]:
    """`GET /sim/map/<scenario>` on the running server: status, body, CORS origin header."""

    def get() -> tuple[int, bytes, str]:
        connection = http.client.HTTPConnection(station.address, timeout=10)
        try:
            connection.request(
                "GET", f"/sim/map/{scenario}", headers={"origin": "http://localhost:5173"}
            )
            response = connection.getresponse()
            return (
                response.status,
                response.read(),
                response.getheader("access-control-allow-origin") or "",
            )
        finally:
            connection.close()

    return await asyncio.to_thread(get)


async def test_a_flying_drone_s_map_is_served_in_the_follow_view(tmp_path: Path) -> None:
    # Given nest-sw-d1 reported climbing while the page streams its frames to the bridge
    async with a_fleet_station(tmp_path) as station, station.a_linked_page() as sim:
        await station.reports(sim, 2.5, SW_D1, drone_frame(SW_D1, "climbing", (-40.0, -20.0, 3.0)))
        a_perception(station.rig.perception).opened(SCENARIO).streams(*blocks((SW_D1, 3)))

        # When the chat asks for the scenario's live map
        status, body, origin = await get_map(station)

    # Then it is nest-sw-d1's climbing map of 3 points, drawn as a follow-view image
    served = json.loads(body)
    assert (status, served["drone_id"], served["phase"], served["points"]) == (
        200,
        SW_D1,
        "climbing",
        3,
    )
    assert pixels_of(served["png"]).shape[:2] == (HEIGHT, WIDTH)
    assert origin == "http://localhost:5173"


async def test_a_docked_drone_s_map_is_not_served(tmp_path: Path) -> None:
    # Given nest-sw-d1 reported docked while the page streams its frames to the bridge
    async with a_fleet_station(tmp_path) as station, station.a_linked_page() as sim:
        await station.reports(sim, 1.0, SW_D1, drone_frame(SW_D1, "docked", (-40.0, -20.0, 0.0)))
        a_perception(station.rig.perception).opened(SCENARIO).streams(*blocks((SW_D1, 3)))

        # When the chat asks for the scenario's live map
        status, body, _ = await get_map(station)

    # Then there is none yet
    assert (status, body) == (204, b"")


async def test_no_map_is_served_while_no_page_streams_the_scenario(tmp_path: Path) -> None:
    # Given the station with no page streaming to its bridge
    async with a_fleet_station(tmp_path) as station:
        # When the chat asks for the scenario's live map
        status, _, _ = await get_map(station)

    # Then there is none
    assert status == 204


async def test_the_map_of_an_unknown_scenario_is_not_found(tmp_path: Path) -> None:
    # Given the station
    async with a_fleet_station(tmp_path) as station:
        # When the chat asks for the live map of a scenario it does not have
        status, _, _ = await get_map(station, "no-such-scene")

    # Then it is not found
    assert status == 404
