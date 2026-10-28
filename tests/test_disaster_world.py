"""Disaster-block scoring frame: ground truth, SDF poses, and the survey plan.

The scene is a fictional civilian search-and-rescue block. These tests
do not start Gazebo or PX4. They pin the files an operator launches and
the JSON a demo uses to score detections.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from surmap.simulation.disaster_world import (
    DisasterGroundTruth,
    ModelPose,
    PersonGroundTruth,
    RoadGroundTruth,
    SurveyPlan,
    disaster_world_sdf,
    enu_to_wgs84,
    load_disaster_ground_truth,
    load_survey_plan,
    world_model_poses,
)

PX4_LATITUDE_DEG = 47.397971057728974
PX4_LONGITUDE_DEG = 8.546163739800146
PX4_ELEVATION_M = 488.0
SURVEY_ALTITUDE_M = 12.0
SURVEY_SPEED_M_S = 4.0
CROSS_TRACK_M = 8.0

# North-south lanes at x = -24, -12, 0, 12, 24, between y = 18 and y = 100.
LAWNMOWER_ENU_M = (
    (-24.0, 18.0),
    (-24.0, 100.0),
    (-12.0, 100.0),
    (-12.0, 18.0),
    (0.0, 18.0),
    (0.0, 100.0),
    (12.0, 100.0),
    (12.0, 18.0),
    (24.0, 18.0),
    (24.0, 100.0),
)

TEXTURES = frozenset(
    {
        "disaster_block_materials/brick.png",
        "disaster_block_materials/asphalt.png",
        "disaster_block_materials/concrete.png",
        "disaster_block_materials/rubble.png",
        "disaster_block_materials/dirt.png",
    }
)


def test_one_hundred_metres_north_of_the_px4_anchor_shifts_latitude_only() -> None:
    # Given the PX4 SITL spherical anchor baked into enu_to_wgs84
    # When a point 100 m due north of that anchor is projected
    latitude_deg, longitude_deg, altitude_m = enu_to_wgs84(0.0, 100.0, 0.0)

    # Then only latitude moves, by the WGS84 meridional arc of 100 m
    assert latitude_deg == pytest.approx(47.398870511394634, abs=1e-12)
    assert longitude_deg == pytest.approx(PX4_LONGITUDE_DEG, abs=1e-12)
    assert altitude_m == pytest.approx(PX4_ELEVATION_M, abs=1e-9)


def test_one_hundred_metres_east_of_the_px4_anchor_shifts_longitude_only() -> None:
    # Given the same anchor
    # When a point 100 m due east is projected
    latitude_deg, longitude_deg, altitude_m = enu_to_wgs84(100.0, 0.0, 0.0)

    # Then only longitude moves, by the WGS84 parallel arc of 100 m
    assert latitude_deg == pytest.approx(PX4_LATITUDE_DEG, abs=1e-12)
    assert longitude_deg == pytest.approx(8.547488428816326, abs=1e-12)
    assert altitude_m == pytest.approx(PX4_ELEVATION_M, abs=1e-9)


def test_survivors_stand_lie_and_wave_in_the_open_streets() -> None:
    # Given the scoring contract for people the demo must find
    # When the ground-truth file is loaded
    people = {person.id: person for person in load_disaster_ground_truth().people}

    # Then six figures cover standing, lying, and waving at these map points
    assert len(people) == 6
    standing_south = people["survivor_standing_avenue_south"]
    assert standing_south.pose == "standing"
    assert _xy(standing_south) == (-4.2, 24.0)
    assert standing_south.yaw_rad == pytest.approx(-math.pi / 2)

    lying_flood = people["survivor_lying_flood_edge"]
    assert lying_flood.pose == "lying"
    assert _xy(lying_flood) == (1.5, 43.5)
    assert lying_flood.yaw_rad == pytest.approx(math.pi / 2)

    waving_plaza = people["survivor_waving_plaza"]
    assert waving_plaza.pose == "waving"
    assert _xy(waving_plaza) == (-2.5, 66.0)
    assert waving_plaza.yaw_rad == pytest.approx(-math.pi / 2)

    standing_collapse = people["survivor_standing_collapse"]
    assert standing_collapse.pose == "standing"
    assert _xy(standing_collapse) == (6.5, 56.0)
    assert standing_collapse.yaw_rad == pytest.approx(math.pi)

    lying_north = people["survivor_lying_north_blockage"]
    assert lying_north.pose == "lying"
    assert _xy(lying_north) == (-1.2, 74.0)
    assert lying_north.yaw_rad == pytest.approx(math.pi / 2)

    waving_east = people["survivor_waving_east_corner"]
    assert waving_east.pose == "waving"
    assert _xy(waving_east) == (10.0, 63.5)
    assert waving_east.yaw_rad == pytest.approx(math.pi)


def test_roads_name_a_clear_lane_a_flood_and_two_blockages() -> None:
    # Given the scoring contract for the street grid
    # When the ground-truth file is loaded
    roads = {road.id: road for road in load_disaster_ground_truth().roads}

    # Then the avenue approach and the west cross street are passable
    south = roads["avenue_south_clear"]
    assert south.kind == "passable"
    assert south.passable is True
    assert _xy(south) == (0.0, 20.0)
    assert south.length_m == pytest.approx(10.0)
    assert south.width_m == pytest.approx(12.0)
    assert south.yaw_rad == pytest.approx(math.pi / 2)

    west = roads["cross_west_clear"]
    assert west.kind == "passable"
    assert west.passable is True
    assert _xy(west) == (-16.0, 60.0)
    assert west.yaw_rad == pytest.approx(0.0)

    # And the south avenue is flooded, the east cross street and north avenue blocked
    flood = roads["avenue_flood"]
    assert flood.kind == "flooded"
    assert flood.passable is False
    assert _xy(flood) == (1.0, 35.0)
    assert flood.length_m == pytest.approx(14.0)
    assert flood.width_m == pytest.approx(8.0)
    assert flood.yaw_rad == pytest.approx(math.pi / 2)

    debris = roads["cross_east_debris"]
    assert debris.kind == "blocked"
    assert debris.passable is False
    assert _xy(debris) == (18.0, 60.0)
    assert debris.yaw_rad == pytest.approx(0.0)

    pole = roads["avenue_north_pole"]
    assert pole.kind == "blocked"
    assert pole.passable is False
    assert _xy(pole) == (0.0, 84.0)
    assert pole.yaw_rad == pytest.approx(math.pi / 2)


def test_each_scoring_fix_is_the_map_point_on_the_px4_anchor() -> None:
    # Given ground truth that claims WGS84 fixes for every scored point
    truth = load_disaster_ground_truth()

    # When the anchor is read off the file
    # Then it is the PX4 SITL origin, and every fix matches that point's ENU offset
    assert truth.world == "disaster_block"
    assert truth.surface_model == "EARTH_WGS84"
    assert truth.world_frame_orientation == "ENU"
    assert truth.heading_deg == pytest.approx(0.0)
    assert truth.latitude_deg == pytest.approx(PX4_LATITUDE_DEG)
    assert truth.longitude_deg == pytest.approx(PX4_LONGITUDE_DEG)
    assert truth.elevation_m == pytest.approx(PX4_ELEVATION_M)
    assert_records_match_anchor(truth)


def test_scored_models_are_static_at_the_ground_truth_pose() -> None:
    # Given the world SDF and the scoring file
    truth = load_disaster_ground_truth()
    poses = world_model_poses(disaster_world_sdf())

    # When each scored id is looked up as a top-level model
    # Then that model is static and sits on the ground-truth pose
    assert_models_sit_on_records(poses, truth)


def test_world_sdf_is_harmonic_and_uses_the_px4_anchor() -> None:
    # Given the disaster-block world file
    root = ET.fromstring(disaster_world_sdf().read_text(encoding="utf-8"))

    # When the SDF header and spherical coordinates are read
    # Then the world is Harmonic SDF 1.9 named disaster_block at the PX4 anchor
    assert root.tag == "sdf"
    assert root.get("version") == "1.9"
    world = root.find("world")
    assert world is not None
    assert world.get("name") == "disaster_block"
    spherical = world.find("spherical_coordinates")
    assert spherical is not None
    assert _child_text(spherical, "surface_model") == "EARTH_WGS84"
    assert _child_text(spherical, "world_frame_orientation") == "ENU"
    assert float(_child_text(spherical, "latitude_deg")) == pytest.approx(PX4_LATITUDE_DEG)
    assert float(_child_text(spherical, "longitude_deg")) == pytest.approx(PX4_LONGITUDE_DEG)
    assert float(_child_text(spherical, "elevation")) == pytest.approx(PX4_ELEVATION_M)
    assert float(_child_text(spherical, "heading_deg")) == pytest.approx(0.0)


def test_albedo_maps_resolve_next_to_the_world_file() -> None:
    # Given albedo maps referenced by the world
    sdf_path = disaster_world_sdf()
    root = ET.fromstring(sdf_path.read_text(encoding="utf-8"))
    maps = [node.text.strip() for node in root.iter("albedo_map") if node.text and node.text.strip()]

    # When each path is resolved beside the SDF
    # Then the brick, asphalt, concrete, rubble, and dirt textures are files
    assert TEXTURES <= set(maps)
    assert_textures_exist(sdf_path.parent, maps)


def test_survey_plan_is_a_twelve_metre_lawnmower() -> None:
    # Given the QGroundControl plan the operator uploads
    plan = load_survey_plan()

    # When the mission items are read in order
    # Then takeoff, the contracted lawnmower at 12 m, and RTL are the whole mission
    assert plan.cruise_speed_m_s == pytest.approx(SURVEY_SPEED_M_S)
    assert plan.home_latitude_deg == pytest.approx(PX4_LATITUDE_DEG)
    assert plan.home_longitude_deg == pytest.approx(PX4_LONGITUDE_DEG)
    assert plan.home_altitude_m == pytest.approx(PX4_ELEVATION_M)
    assert plan.items[0].command == 22
    assert plan.items[0].altitude_m == pytest.approx(SURVEY_ALTITUDE_M)
    assert plan.items[-1].command == 20
    assert_lawnmower(plan)


def test_every_survivor_is_inside_the_survey_cross_track() -> None:
    # Given survivors on the streets and the lawnmower that flies those streets
    people = load_disaster_ground_truth().people
    points = _waypoint_enu(load_survey_plan())

    # When each person is measured to the nearest plan segment
    # Then none sits more than 8 m off the path
    assert_people_within_cross_track(people, points, CROSS_TRACK_M)


def test_launch_script_selects_the_stereo_airframe_and_does_not_fly() -> None:
    # Given the single SITL launch script
    script = Path(__file__).resolve().parents[1] / "scripts" / "launch_disaster_sitl.sh"
    text = script.read_text(encoding="utf-8")

    # When its command line is read
    # Then it starts the stereo model in disaster_block and never arms or uploads a mission
    assert "PX4_GZ_WORLD=disaster_block" in text
    assert "PX4_SIM_MODEL=x500_surmap_stereo" in text
    assert "disaster_block.sdf" in text
    assert "commander" not in text
    assert "mavlink" not in text.lower()
    assert "HEADLESS" not in text


def _xy(record: PersonGroundTruth | RoadGroundTruth) -> tuple[float, float]:
    return (record.map_enu.x_m, record.map_enu.y_m)


def assert_records_match_anchor(truth: DisasterGroundTruth) -> None:
    """Every stored fix equals the ENU offset of that point from the anchor."""
    for record in (*truth.people, *truth.roads):
        latitude_deg, longitude_deg, altitude_m = enu_to_wgs84(
            record.map_enu.x_m,
            record.map_enu.y_m,
            record.map_enu.z_m,
        )
        assert record.latitude_deg == pytest.approx(latitude_deg, abs=1e-9)
        assert record.longitude_deg == pytest.approx(longitude_deg, abs=1e-9)
        assert record.altitude_m == pytest.approx(altitude_m, abs=1e-6)
        assert record.map_enu.z_m == pytest.approx(0.0)


def assert_models_sit_on_records(
    poses: dict[str, ModelPose],
    truth: DisasterGroundTruth,
) -> None:
    """Each scored id is a static model on the ground-truth pose."""
    for record in (*truth.people, *truth.roads):
        pose = poses[record.id]
        assert pose.static is True
        assert pose.x_m == pytest.approx(record.map_enu.x_m, abs=1e-3)
        assert pose.y_m == pytest.approx(record.map_enu.y_m, abs=1e-3)
        assert pose.z_m == pytest.approx(record.map_enu.z_m, abs=1e-3)
        assert pose.roll_rad == pytest.approx(0.0, abs=1e-3)
        assert pose.pitch_rad == pytest.approx(0.0, abs=1e-3)
        assert pose.yaw_rad == pytest.approx(record.yaw_rad, abs=1e-3)


def assert_textures_exist(world_dir: Path, maps: list[str]) -> None:
    for relative in maps:
        assert (world_dir / relative).is_file(), relative


def assert_lawnmower(plan: SurveyPlan) -> None:
    """Waypoints are exactly the contracted ENU grid at the survey altitude."""
    waypoints = [item for item in plan.items if item.command == 16]
    assert [item.command for item in plan.items[1:-1]] == [16] * len(waypoints)
    assert len(waypoints) == len(LAWNMOWER_ENU_M)
    for item, (east_m, north_m) in zip(waypoints, LAWNMOWER_ENU_M, strict=True):
        assert item.altitude_m == pytest.approx(SURVEY_ALTITUDE_M)
        assert item.frame == 3
        assert item.map_enu is not None
        assert item.map_enu.x_m == pytest.approx(east_m, abs=0.05)
        assert item.map_enu.y_m == pytest.approx(north_m, abs=0.05)
        assert item.map_enu.z_m == pytest.approx(SURVEY_ALTITUDE_M, abs=1e-6)


def assert_people_within_cross_track(
    people: tuple[PersonGroundTruth, ...],
    points: list[tuple[float, float]],
    metres: float,
) -> None:
    for person in people:
        distance_m = _nearest_segment_distance_m(
            person.map_enu.x_m,
            person.map_enu.y_m,
            points,
        )
        assert distance_m <= metres


def _waypoint_enu(plan: SurveyPlan) -> list[tuple[float, float]]:
    return [
        (item.map_enu.x_m, item.map_enu.y_m)
        for item in plan.items
        if item.command == 16 and item.map_enu is not None
    ]


def _nearest_segment_distance_m(
    east_m: float,
    north_m: float,
    points: list[tuple[float, float]],
) -> float:
    best = min(math.hypot(east_m - x_m, north_m - y_m) for x_m, y_m in points)
    for (ax, ay), (bx, by) in zip(points, points[1:], strict=False):
        best = min(best, _distance_to_segment_m(east_m, north_m, ax, ay, bx, by))
    return best


def _distance_to_segment_m(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    vx = bx - ax
    vy = by - ay
    length2 = vx * vx + vy * vy
    if length2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / length2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _child_text(parent: ET.Element, tag: str) -> str:
    child = parent.find(tag)
    assert child is not None
    assert child.text is not None
    return child.text.strip()
