"""Vehicles in a scenario: the `vehicle` element's rules (the renderer's `vehicle.rs` and
`SceneManifest::validate_vehicles` apply the same) and the `street-traffic` preset."""

from __future__ import annotations

import copy
from collections.abc import Mapping

from surmap.simulation.behaviour_tree import validate_behaviour
from surmap.simulation.manifest_checks import (
    Manifest,
    ScenarioInvalid,
    number,
    object_list,
)

VEHICLE_CLASSES = ("car", "bus", "truck", "train", "boat", "ship")
GLTF_SUFFIXES = (".glb", ".gltf")
# The bus model is white; a school bus is yellow, which the on-board detectors read as a bus far
# more often than white or red (docs/simulation/bevy-simulation.md § On-board detectors).
SCHOOL_BUS_YELLOW = [1.0, 0.78, 0.1]
BALLAST: dict[str, object] = {
    "color": [0.45, 0.42, 0.38],
    "perceptual_roughness": 0.95,
    "reflectance": 0.2,
}


def _where(element: Mapping[str, object]) -> str:
    return f"vehicle {element.get('id')}"


def _gltf(path: object, where: str) -> None:
    if not isinstance(path, str) or not path.endswith(GLTF_SUFFIXES):
        raise ScenarioInvalid(f"{where}: glb {path!r} must be a glTF (.glb/.gltf) file")
    parts = path.split("/")
    if path.startswith("/") or ".." in parts or "" in parts:
        raise ScenarioInvalid(f"{where}: glb {path!r} must stay inside the assets")


def _cars(element: Mapping[str, object], where: str) -> None:
    cars = element.get("cars", 0)
    if isinstance(cars, bool) or not isinstance(cars, int) or cars < 0:
        raise ScenarioInvalid(f"{where}: cars must be a whole number, 0 or more")
    if cars > 0 and element.get("class") != "train":
        raise ScenarioInvalid(f"{where}: cars only on a train, not on a {element.get('class')}")


def _numbers(value: object, what: str, where: str, count: int) -> None:
    if not isinstance(value, list) or len(value) != count:
        raise ScenarioInvalid(f"{where}: {what} must be {count} numbers")
    for item in value:
        number(item, f"{where} {what}")


def validate_vehicle(element: Mapping[str, object]) -> None:
    """Raise `ScenarioInvalid` for a vehicle the renderer would refuse: an unknown `class`,
    `cars` on anything but a train, a `glb` that is not a relative glTF path, or a tree that is
    not valid for a body on the ground."""
    where = _where(element)
    if element.get("class") not in VEHICLE_CLASSES:
        raise ScenarioInvalid(
            f"{where}: class {element.get('class')!r} must be one of {VEHICLE_CLASSES}"
        )
    _cars(element, where)
    _numbers(element.get("position_enu"), "position_enu", where, 3)
    if "yaw_deg" in element:
        number(element["yaw_deg"], f"{where} yaw_deg")
    if element.get("glb") is not None:
        _gltf(element["glb"], where)
    if "tint" in element:
        _numbers(element["tint"], "tint", where, 3)
    if element.get("behaviour") is not None:
        try:
            validate_behaviour(element["behaviour"], "object")
        except ScenarioInvalid as exc:
            raise ScenarioInvalid(f"{where}: {exc}") from exc


def _drive(*path: list[float], speed: float) -> dict[str, object]:
    return {"node": "follow_path", "enu": [list(point) for point in path], "speed_m_s": speed}


def _shuttle(
    there: list[float], back: list[float], speed: float, pause_s: float = 10.0
) -> dict[str, object]:
    """A drive that runs `there`, waits, runs `back`, and repeats."""
    return {
        "node": "repeat",
        "child": {
            "node": "sequence",
            "children": [
                _drive(there, speed=speed),
                {"node": "idle", "s": pause_s},
                _drive(back, speed=speed),
            ],
        },
    }


def _vehicle(
    vehicle_id: str,
    vehicle_class: str,
    position: list[float],
    yaw_deg: float,
    **fields: object,
) -> dict[str, object]:
    return {
        "kind": "vehicle",
        "id": vehicle_id,
        "class": vehicle_class,
        "position_enu": [*position, 0.0],
        "yaw_deg": yaw_deg,
        **fields,
    }


def street_traffic(block: Manifest) -> Manifest:
    """The disaster block with traffic: cars on the avenue, a bus and a truck on the cross street,
    a parked car, and a six-carriage train on a rail line along the block's west edge."""
    edited: Manifest = copy.deepcopy(block)
    materials = copy.deepcopy(block.get("materials"))
    if not isinstance(materials, dict):
        raise ScenarioInvalid("materials must be an object")
    materials["ballast"] = dict(BALLAST)
    rail: dict[str, object] = {
        "kind": "box",
        "id": "rail-line",
        "material": "ballast",
        "size_m": [3.0, 200.0, 0.08],
        "position_enu": [-62.0, 45.0, 0.0],
        "collider": True,
    }
    vehicles = [
        _vehicle(
            "car-north-1",
            "car",
            [2.5, -40.0],
            90.0,
            behaviour=_shuttle([2.5, 120.0], [2.5, -40.0], 10.0),
        ),
        _vehicle(
            "car-north-2",
            "car",
            [2.5, 20.0],
            90.0,
            behaviour=_shuttle([2.5, 130.0], [2.5, 20.0], 12.0),
        ),
        _vehicle(
            "truck-cross-1",
            "truck",
            [-45.0, 57.5],
            0.0,
            behaviour=_shuttle([45.0, 57.5], [-45.0, 57.5], 9.0),
        ),
        _vehicle(
            "bus-cross-1",
            "bus",
            [-45.0, 62.5],
            0.0,
            tint=SCHOOL_BUS_YELLOW,
            behaviour=_shuttle([45.0, 62.5], [-45.0, 62.5], 8.0),
        ),
        _vehicle("car-parked-1", "car", [7.0, 30.0], 90.0),
        _vehicle(
            "freight",
            "train",
            [-62.0, -50.0],
            90.0,
            cars=6,
            behaviour=_drive([-62.0, 140.0], speed=15.0),
        ),
    ]
    edited["materials"] = materials
    edited["elements"] = [*object_list(block, "elements"), rail, *vehicles]
    return edited
