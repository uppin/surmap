"""Map-floor manifest edits: validation, setting and clearing a scenario's floor.

Kept apart from `scenario_manifest` (the scene's validator and preset builder) so
that file stays within the repository's file-length gate; callers import these
names from here.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from math import cos, radians

from surmap.simulation.manifest_checks import Manifest, ScenarioInvalid, is_relative_path, number


def _number(value: object, what: str) -> float:
    return number(value, what)


def _relative(path: object, what: str) -> str:
    if not isinstance(path, str) or not path:
        raise ScenarioInvalid(f"{what} must be a path")
    if not is_relative_path(path):
        raise ScenarioInvalid(f"{what} {path!r} must stay inside the assets")
    return path


def validate_map_floor(manifest: Mapping[str, object]) -> None:
    floor = manifest.get("map_floor")
    if floor is None:
        return
    if not isinstance(floor, dict):
        raise ScenarioInvalid("map_floor must be an object")
    for corner in ("sw", "ne"):
        point = floor.get(corner)
        if not isinstance(point, list) or len(point) != 2:
            raise ScenarioInvalid(f"map_floor {corner} must be [lat, lon]")
        lat = _number(point[0], f"map_floor {corner} lat")
        lon = _number(point[1], f"map_floor {corner} lon")
        if not -85.0 <= lat <= 85.0 or not -180.0 <= lon <= 180.0:
            raise ScenarioInvalid(f"map_floor {corner} is outside the map's range")
    sw, ne = floor["sw"], floor["ne"]
    assert isinstance(sw, list) and isinstance(ne, list)
    if not (float(sw[0]) < float(ne[0]) and float(sw[1]) < float(ne[1])):
        raise ScenarioInvalid("map_floor sw must be south and west of ne")
    texture = _relative(floor.get("texture"), "map_floor texture")
    if not texture.endswith(".png"):
        raise ScenarioInvalid(f"map_floor texture {texture!r} must be a .png")
    zoom = floor.get("zoom")
    if isinstance(zoom, bool) or not isinstance(zoom, int) or not 0 <= zoom <= 18:
        raise ScenarioInvalid("map_floor zoom must be an integer in 0..18")
    # Same size cap the renderer applies (scene_manifest.rs MapFloor::validate):
    # 111 320 m per degree of latitude, longitude scaled by cos(centre latitude).
    centre_lat = (float(sw[0]) + float(ne[0])) / 2.0
    north_m = (float(ne[0]) - float(sw[0])) * 111_320.0
    east_m = (float(ne[1]) - float(sw[1])) * 111_320.0 * cos(radians(centre_lat))
    if east_m > 1000.0 or north_m > 1000.0:
        raise ScenarioInvalid("map_floor is at most 1000 m a side")


def set_map_floor(
    manifest: Mapping[str, object],
    *,
    sw: tuple[float, float],
    ne: tuple[float, float],
    texture: str,
    zoom: int,
) -> Manifest:
    """A new manifest whose floor is the map cropped to the `sw`..`ne` GPS bbox.

    The floor replaces the preset ground: the `ground` box element is removed,
    because its opaque top at 0 m would hide the floor plane under it. The
    renderer gives the floor itself a fixed collider, so nothing loses the
    ground it stands on.
    """
    edited: Manifest = copy.deepcopy(dict(manifest))
    edited["map_floor"] = {
        "sw": [sw[0], sw[1]],
        "ne": [ne[0], ne[1]],
        "texture": texture,
        "zoom": zoom,
    }
    elements = edited.get("elements")
    if isinstance(elements, list):
        removed = [e for e in elements if _is_ground_box(e)]
        if removed:
            floor = edited["map_floor"]
            assert isinstance(floor, dict)
            floor["replaced_ground"] = removed
        edited["elements"] = [e for e in elements if not _is_ground_box(e)]
    from surmap.simulation.manifest_validation import validate_manifest

    validate_manifest(edited)
    return edited


_GROUND_IDS = ("ground", "block-ground", "apron")


def _is_ground_box(element: object) -> bool:
    """A preset's ground box: flagged `ground`, or a legacy ground id (pre-flag manifests)."""
    if not isinstance(element, dict) or element.get("kind") != "box":
        return False
    return element.get("ground") is True or element.get("id") in _GROUND_IDS


def clear_map_floor(manifest: Mapping[str, object]) -> Manifest:
    """A new manifest with no map floor; the ground boxes the floor replaced come back.

    `set_map_floor` records what it removed in `map_floor.replaced_ground`, so clearing
    restores the preset's own ground (an apron, a block ground) rather than inventing one.
    A floor set by hand, with nothing recorded, clears to no ground at all.
    """
    edited: Manifest = copy.deepcopy(dict(manifest))
    floor = edited.pop("map_floor", None)
    restored: list[object] = []
    if isinstance(floor, dict) and isinstance(floor.get("replaced_ground"), list):
        restored = list(floor["replaced_ground"])
    elements = edited.get("elements")
    items = list(elements) if isinstance(elements, list) else []
    present = {e.get("id") for e in items if isinstance(e, dict)}
    edited["elements"] = [
        e for e in restored if not (isinstance(e, dict) and e.get("id") in present)
    ] + items
    from surmap.simulation.manifest_validation import validate_manifest

    validate_manifest(edited)
    return edited
