"""Ground truth and survey plan for the disaster-block Gazebo world.

SurMap stays passive. This module reads the world, the scoring JSON,
and the QGroundControl plan an operator loads. It does not arm a
vehicle or upload a mission.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import cast

WGS84_A_M = 6378137.0
WGS84_E2 = 6.69437999014e-3

# PX4 SITL default world anchor (Zurich test site). The block is fictional.
ANCHOR_LATITUDE_DEG = 47.397971057728974
ANCHOR_LONGITUDE_DEG = 8.546163739800146
ANCHOR_ELEVATION_M = 488.0

_FIX_TOLERANCE_DEG = 1e-8
_ALT_TOLERANCE_M = 1e-4
_POSES = ("standing", "lying", "waving")
_ROAD_KINDS = ("passable", "blocked", "flooded")


def disaster_world_dir() -> Path:
    """Directory of the disaster-block SDF, textures, JSON, and plan."""
    return Path(__file__).resolve().parents[3] / "docs" / "simulation" / "gz" / "worlds"


def disaster_world_sdf() -> Path:
    """Harmonic world file PX4 opens as ``disaster_block.sdf``."""
    return disaster_world_dir() / "disaster_block.sdf"


def disaster_ground_truth_path() -> Path:
    """Scoring JSON: people and roads in map ENU and WGS84."""
    return disaster_world_dir() / "disaster_block_ground_truth.json"


def disaster_survey_plan_path() -> Path:
    """QGroundControl plan. SurMap does not upload it."""
    return disaster_world_dir() / "disaster_block_survey.plan"


def enu_to_wgs84(
    east_m: float,
    north_m: float,
    up_m: float = 0.0,
    *,
    latitude_deg: float = ANCHOR_LATITUDE_DEG,
    longitude_deg: float = ANCHOR_LONGITUDE_DEG,
    elevation_m: float = ANCHOR_ELEVATION_M,
) -> tuple[float, float, float]:
    """Local ENU metres to WGS84, heading 0 (+x east, +y north).

    Linearised at the anchor with the WGS84 meridional and prime-vertical
    radii. Millimetre-level inside this block.
    """
    lat0 = math.radians(latitude_deg)
    sin_lat = math.sin(lat0)
    one_minus = 1.0 - WGS84_E2 * sin_lat * sin_lat
    prime_vertical_m = WGS84_A_M / math.sqrt(one_minus)
    meridional_m = WGS84_A_M * (1.0 - WGS84_E2) / (one_minus**1.5)
    latitude = latitude_deg + math.degrees(north_m / meridional_m)
    longitude = longitude_deg + math.degrees(east_m / (prime_vertical_m * math.cos(lat0)))
    return latitude, longitude, elevation_m + up_m


def wgs84_to_enu(
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float,
    *,
    anchor_latitude_deg: float = ANCHOR_LATITUDE_DEG,
    anchor_longitude_deg: float = ANCHOR_LONGITUDE_DEG,
    anchor_elevation_m: float = ANCHOR_ELEVATION_M,
) -> tuple[float, float, float]:
    """Inverse of :func:`enu_to_wgs84` at the same anchor."""
    lat0 = math.radians(anchor_latitude_deg)
    sin_lat = math.sin(lat0)
    one_minus = 1.0 - WGS84_E2 * sin_lat * sin_lat
    prime_vertical_m = WGS84_A_M / math.sqrt(one_minus)
    meridional_m = WGS84_A_M * (1.0 - WGS84_E2) / (one_minus**1.5)
    north_m = math.radians(latitude_deg - anchor_latitude_deg) * meridional_m
    east_m = math.radians(longitude_deg - anchor_longitude_deg) * prime_vertical_m * math.cos(lat0)
    up_m = altitude_m - anchor_elevation_m
    return east_m, north_m, up_m


@dataclass(frozen=True)
class MapEnu:
    """Gazebo world frame: +x east, +y north, +z up, metres."""

    x_m: float
    y_m: float
    z_m: float


@dataclass(frozen=True)
class PersonGroundTruth:
    """One human figure the demo can score."""

    id: str
    pose: str
    map_enu: MapEnu
    yaw_rad: float
    latitude_deg: float
    longitude_deg: float
    altitude_m: float


@dataclass(frozen=True)
class RoadGroundTruth:
    """One scored street segment: passable, flooded, or blocked."""

    id: str
    kind: str
    passable: bool
    map_enu: MapEnu
    length_m: float
    width_m: float
    yaw_rad: float
    latitude_deg: float
    longitude_deg: float
    altitude_m: float


@dataclass(frozen=True)
class DisasterGroundTruth:
    """Scoring file for the disaster block, tied to its spherical anchor."""

    world: str
    people: tuple[PersonGroundTruth, ...]
    roads: tuple[RoadGroundTruth, ...]
    latitude_deg: float
    longitude_deg: float
    elevation_m: float
    heading_deg: float
    world_frame_orientation: str
    surface_model: str


@dataclass(frozen=True)
class ModelPose:
    """Top-level model pose in the world SDF."""

    name: str
    static: bool
    x_m: float
    y_m: float
    z_m: float
    roll_rad: float
    pitch_rad: float
    yaw_rad: float


@dataclass(frozen=True)
class SurveyItem:
    """One QGroundControl mission item.

    ``map_enu.z_m`` is altitude above the home anchor, the same number
    the plan stores as relative altitude. RTL has no map position.
    """

    command: int
    frame: int
    altitude_m: float
    latitude_deg: float
    longitude_deg: float
    map_enu: MapEnu | None


@dataclass(frozen=True)
class SurveyPlan:
    """Lawnmower the operator uploads from QGroundControl."""

    cruise_speed_m_s: float
    home_latitude_deg: float
    home_longitude_deg: float
    home_altitude_m: float
    items: tuple[SurveyItem, ...]


def load_disaster_ground_truth(path: Path | None = None) -> DisasterGroundTruth:
    """Load scoring JSON and reject fixes that disagree with the anchor."""
    truth_path = path if path is not None else disaster_ground_truth_path()
    payload = _object(json.loads(truth_path.read_text(encoding="utf-8")), "ground truth")
    spherical = _object(payload["spherical_coordinates"], "spherical_coordinates")
    people = tuple(
        _person(item, index) for index, item in enumerate(_list(payload["people"], "people"))
    )
    roads = tuple(_road(item, index) for index, item in enumerate(_list(payload["roads"], "roads")))
    _unique_ids([person.id for person in people] + [road.id for road in roads])
    return DisasterGroundTruth(
        world=_str(payload["world"], "world"),
        people=people,
        roads=roads,
        latitude_deg=_float(spherical["latitude_deg"], "latitude_deg"),
        longitude_deg=_float(spherical["longitude_deg"], "longitude_deg"),
        elevation_m=_float(spherical["elevation_m"], "elevation_m"),
        heading_deg=_float(spherical["heading_deg"], "heading_deg"),
        world_frame_orientation=_str(
            spherical["world_frame_orientation"],
            "world_frame_orientation",
        ),
        surface_model=_str(spherical["surface_model"], "surface_model"),
    )


def world_model_poses(sdf_path: Path) -> dict[str, ModelPose]:
    """Direct child models of the world, keyed by name."""
    root = ET.fromstring(sdf_path.read_text(encoding="utf-8"))
    world = root.find("world")
    if world is None:
        raise ValueError(f"{sdf_path} has no world element")
    poses: dict[str, ModelPose] = {}
    for model in world.findall("model"):
        name = model.get("name")
        if not name:
            raise ValueError(f"{sdf_path} has a model without a name")
        if name in poses:
            raise ValueError(f"duplicate model {name}")
        pose_text = model.findtext("pose")
        if pose_text is None:
            raise ValueError(f"model {name} has no pose")
        parts = [float(part) for part in pose_text.split()]
        if len(parts) != 6:
            raise ValueError(f"model {name} pose must have 6 numbers")
        static_text = (model.findtext("static") or "").strip().lower()
        poses[name] = ModelPose(
            name=name,
            static=static_text == "true",
            x_m=parts[0],
            y_m=parts[1],
            z_m=parts[2],
            roll_rad=parts[3],
            pitch_rad=parts[4],
            yaw_rad=parts[5],
        )
    return poses


def load_survey_plan(path: Path | None = None) -> SurveyPlan:
    """Load a QGroundControl plan and project waypoints into map ENU."""
    plan_path = path if path is not None else disaster_survey_plan_path()
    payload = _object(json.loads(plan_path.read_text(encoding="utf-8")), "plan")
    mission = _object(payload["mission"], "mission")
    home = _list(mission["plannedHomePosition"], "plannedHomePosition")
    if len(home) != 3:
        raise ValueError("plannedHomePosition must be latitude, longitude, altitude")
    items = tuple(
        _survey_item(item, index) for index, item in enumerate(_list(mission["items"], "items"))
    )
    if not items:
        raise ValueError("survey plan has no items")
    return SurveyPlan(
        cruise_speed_m_s=_float(mission["cruiseSpeed"], "cruiseSpeed"),
        home_latitude_deg=_float(home[0], "home latitude"),
        home_longitude_deg=_float(home[1], "home longitude"),
        home_altitude_m=_float(home[2], "home altitude"),
        items=items,
    )


def _person(raw: object, index: int) -> PersonGroundTruth:
    body = _object(raw, f"people[{index}]")
    pose = _str(body["pose"], f"people[{index}].pose")
    if pose not in _POSES:
        raise ValueError(f"people[{index}].pose must be standing, lying, or waving")
    map_enu = _map_enu(body["map_enu_m"], f"people[{index}].map_enu_m")
    person = PersonGroundTruth(
        id=_str(body["id"], f"people[{index}].id"),
        pose=pose,
        map_enu=map_enu,
        yaw_rad=_float(body["yaw_rad"], f"people[{index}].yaw_rad"),
        latitude_deg=_float(body["latitude_deg"], f"people[{index}].latitude_deg"),
        longitude_deg=_float(body["longitude_deg"], f"people[{index}].longitude_deg"),
        altitude_m=_float(body["altitude_m"], f"people[{index}].altitude_m"),
    )
    _check_fix(person.id, map_enu, person.latitude_deg, person.longitude_deg, person.altitude_m)
    return person


def _road(raw: object, index: int) -> RoadGroundTruth:
    label = f"roads[{index}]"
    body = _object(raw, label)
    kind = _str(body["kind"], f"{label}.kind")
    if kind not in _ROAD_KINDS:
        raise ValueError(f"{label}.kind must be passable, blocked, or flooded")
    passable = _bool(body["passable"], f"{label}.passable")
    if kind == "passable" and not passable:
        raise ValueError(f"{label} is passable but passable is false")
    if kind != "passable" and passable:
        raise ValueError(f"{label} is {kind} but passable is true")
    map_enu = _map_enu(body["map_enu_m"], f"{label}.map_enu_m")
    road = RoadGroundTruth(
        id=_str(body["id"], f"{label}.id"),
        kind=kind,
        passable=passable,
        map_enu=map_enu,
        length_m=_float(body["length_m"], f"{label}.length_m"),
        width_m=_float(body["width_m"], f"{label}.width_m"),
        yaw_rad=_float(body["yaw_rad"], f"{label}.yaw_rad"),
        latitude_deg=_float(body["latitude_deg"], f"{label}.latitude_deg"),
        longitude_deg=_float(body["longitude_deg"], f"{label}.longitude_deg"),
        altitude_m=_float(body["altitude_m"], f"{label}.altitude_m"),
    )
    _check_fix(road.id, map_enu, road.latitude_deg, road.longitude_deg, road.altitude_m)
    return road


def _check_fix(
    name: str,
    map_enu: MapEnu,
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float,
) -> None:
    expect_lat, expect_lon, expect_alt = enu_to_wgs84(map_enu.x_m, map_enu.y_m, map_enu.z_m)
    if abs(latitude_deg - expect_lat) > _FIX_TOLERANCE_DEG:
        raise ValueError(f"{name} latitude does not match its map offset")
    if abs(longitude_deg - expect_lon) > _FIX_TOLERANCE_DEG:
        raise ValueError(f"{name} longitude does not match its map offset")
    if abs(altitude_m - expect_alt) > _ALT_TOLERANCE_M:
        raise ValueError(f"{name} altitude does not match its map offset")


def _survey_item(raw: object, index: int) -> SurveyItem:
    body = _object(raw, f"items[{index}]")
    params = _list(body["params"], f"items[{index}].params")
    if len(params) != 7:
        raise ValueError(f"items[{index}].params must have 7 values")
    command = int(_float(body["command"], f"items[{index}].command"))
    frame = int(_float(body["frame"], f"items[{index}].frame"))
    altitude_m = _float(params[6], f"items[{index}].altitude")
    if command == 20:
        return SurveyItem(command, frame, altitude_m, 0.0, 0.0, None)
    latitude_deg = _float(params[4], f"items[{index}].latitude")
    longitude_deg = _float(params[5], f"items[{index}].longitude")
    east_m, north_m, _up_m = wgs84_to_enu(latitude_deg, longitude_deg, ANCHOR_ELEVATION_M)
    return SurveyItem(
        command=command,
        frame=frame,
        altitude_m=altitude_m,
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        map_enu=MapEnu(east_m, north_m, altitude_m),
    )


def _map_enu(raw: object, label: str) -> MapEnu:
    body = _object(raw, label)
    return MapEnu(
        x_m=_float(body["x"], f"{label}.x"),
        y_m=_float(body["y"], f"{label}.y"),
        z_m=_float(body["z"], f"{label}.z"),
    )


def _unique_ids(ids: list[str]) -> None:
    seen: set[str] = set()
    for name in ids:
        if name in seen:
            raise ValueError(f"duplicate ground-truth id {name}")
        seen.add(name)


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return cast(list[object], value)


def _str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be a number")
    return float(value)
