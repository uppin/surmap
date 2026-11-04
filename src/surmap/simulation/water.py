"""Boats and ships in a scenario: water surfaces (`box` elements with `water: true`), the rules that
keep vessels on them (the renderer's `SceneManifest::validate_vessels` applies the same), and the
`flood-rescue` preset."""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence

from surmap.simulation.manifest_checks import Manifest, ScenarioInvalid, number, object_list

VESSEL_CLASSES = ("boat", "ship")
# Nodes a vessel may not use: their points are not known to lie on water when the scene loads.
FORBIDDEN_ON_WATER = ("wander", "flee_from_fire")
# A boat's shuttle along the flood, and the second boat's, against it.
SHUTTLE_NORTH = [[0.0, 90.0], [0.0, 10.0]]
SHUTTLE_SOUTH = [[0.0, 10.0], [0.0, 90.0]]


class Surface:
    """A `water: true` box's footprint and top, as the renderer reads it."""

    def __init__(self, box: Mapping[str, object]) -> None:
        size = _triple(box.get("size_m"))
        position = _triple(box.get("position_enu"))
        self.centre = (position[0], position[1])
        self.half = (size[0] / 2.0, size[1] / 2.0)
        self.yaw = math.radians(number(box.get("yaw_deg", 0.0), "yaw_deg"))
        self.top = position[2] + size[2]

    def contains(self, point: tuple[float, float]) -> bool:
        dx = point[0] - self.centre[0]
        dy = point[1] - self.centre[1]
        cos, sin = math.cos(self.yaw), math.sin(self.yaw)
        local_x = dx * cos + dy * sin
        local_y = -dx * sin + dy * cos
        return abs(local_x) <= self.half[0] and abs(local_y) <= self.half[1]


def water_surfaces(manifest: Mapping[str, object]) -> tuple[Surface, ...]:
    """Every `water: true` box of the scenario, as a surface, in manifest order: what vessels float
    on and what a drone nest may not stand on."""
    # TODO(pr-1): implement
    raise NotImplementedError("pr-1: implement")


def _triple(value: object) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ScenarioInvalid("a box's size_m and position_enu must be three numbers")
    east, north, up = (number(v, "box coordinate") for v in value)
    return east, north, up


def _where(vehicle: Mapping[str, object]) -> str:
    return f"vehicle {vehicle.get('id')}"


def _points(tree: object) -> list[tuple[float, float]]:
    """Every point a tree steers to (`move_to`, `follow_path`), in tree order."""
    if not isinstance(tree, dict):
        return []
    found: list[tuple[float, float]] = []
    if tree.get("node") == "move_to":
        found.append(_point(tree.get("enu")))
    path = tree.get("enu")
    if tree.get("node") == "follow_path" and isinstance(path, list):
        found.extend(_point(p) for p in path)
    for child in _children(tree):
        found.extend(_points(child))
    return found


def _children(tree: Mapping[str, object]) -> list[object]:
    children = tree.get("children")
    if isinstance(children, list):
        return list(children)
    child = tree.get("child")
    return [child] if child is not None else []


def _point(value: object) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ScenarioInvalid("a steered point must be [east, north]")
    return number(value[0], "point east"), number(value[1], "point north")


def _forbidden(tree: object) -> list[str]:
    """The nodes a vessel's tree may not use, in tree order."""
    if not isinstance(tree, dict):
        return []
    found = [str(tree.get("node"))] if tree.get("node") in FORBIDDEN_ON_WATER else []
    for child in _children(tree):
        found.extend(_forbidden(child))
    return found


def _check_water_flag(element: Mapping[str, object]) -> None:
    if "water" in element and not isinstance(element["water"], bool):
        raise ScenarioInvalid(f"{element.get('id')}: water must be true or false")


def validate_vessels(manifest: Mapping[str, object]) -> None:
    """Raise `ScenarioInvalid` when a boat or ship starts off water, steers (`move_to`,
    `follow_path`) to a point off water, or has `wander` / `flee_from_fire` in its tree; or when a
    road or rail vehicle starts on water. The reason names the vehicle and the point. A `water`
    flag that is not a boolean is refused too."""
    boxes = object_list(manifest, "elements")
    for box in boxes:
        if box.get("kind") == "box":
            _check_water_flag(box)
    surfaces = [
        Surface(box) for box in boxes if box.get("kind") == "box" and box.get("water") is True
    ]
    for vehicle in object_list(manifest, "elements"):
        if vehicle.get("kind") != "vehicle":
            continue
        east, north, _ = _triple(vehicle.get("position_enu"))
        start = (east, north)
        on_water = any(surface.contains(start) for surface in surfaces)
        if vehicle.get("class") not in VESSEL_CLASSES:
            if on_water:
                raise ScenarioInvalid(
                    f"{_where(vehicle)}: a {vehicle.get('class')} cannot start on water, at {start}"
                )
            continue
        if not on_water:
            raise ScenarioInvalid(f"{_where(vehicle)}: starts at {start}, off the water")
        tree = vehicle.get("behaviour")
        if tree is None:
            continue
        forbidden = _forbidden(tree)
        if forbidden:
            raise ScenarioInvalid(
                f"{_where(vehicle)}: {forbidden[0]} is not allowed on water, "
                "its points are not known to be on it"
            )
        for point in _points(tree):
            if not any(surface.contains(point) for surface in surfaces):
                raise ScenarioInvalid(f"{_where(vehicle)}: steers to {point}, off the water")


def _shuttle(path: Sequence[Sequence[float]], speed: float) -> dict[str, object]:
    """A drive along `path` that repeats: a boat's run up and down the flood."""
    follow: dict[str, object] = {
        "node": "follow_path",
        "enu": [list(point) for point in path],
        "speed_m_s": speed,
    }
    return {"node": "repeat", "child": follow}


def _boat(
    boat_id: str, start: Sequence[float], path: Sequence[Sequence[float]]
) -> dict[str, object]:
    return {
        "kind": "vehicle",
        "id": boat_id,
        "class": "boat",
        "position_enu": [start[0], start[1], 0.0],
        "behaviour": _shuttle(path, 4.0),
    }


def _survivor() -> dict[str, object]:
    """A survivor standing at the flood's north end, waiting to be reached by boat."""
    return {
        "kind": "person",
        "id": "survivor-flood",
        "position_enu": [0.0, 104.0, 0.0],
        "coat": "coat_yellow",
        "skin": "skin",
    }


def flood_rescue(flood_street: Manifest) -> Manifest:
    """`flood-street` with 0.6 m of floodwater over the avenue, two rescue boats shuttling its
    length, and a survivor waiting at its north end."""
    rescue: Manifest = copy.deepcopy(flood_street)
    elements = object_list(flood_street, "elements")
    floodwater: dict[str, object] = {
        "kind": "box",
        "id": "floodwater",
        "material": "water",
        "size_m": [10.0, 100.0, 0.6],
        "position_enu": [0.0, 50.0, 0.0],
        "water": True,
    }
    rescue["elements"] = [
        *elements,
        floodwater,
        _boat("rescue-boat-1", [0.0, 10.0], SHUTTLE_NORTH),
        _boat("rescue-boat-2", [0.0, 90.0], SHUTTLE_SOUTH),
        _survivor(),
    ]
    validate_vessels(rescue)
    return rescue
