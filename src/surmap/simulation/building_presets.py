"""Building presets on Overture's vocabulary, districts and building fires in scenario manifests.

Facades and roofs are named after Overture's `facade_material` and `roof_material` values; each
is a runtime JSON file under `assets/building/` (a name is the shipped file, a path names any other
file). A district is a preset over an ENU rectangle: the buildings whose centre it holds draw their
style from its weighted mix. The same rules the renderer applies (`scene_manifest/buildings.rs`)
are checked here, so the station never serves a style the simulation would refuse.
"""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from surmap.simulation.manifest_checks import Manifest, ScenarioInvalid, number, object_list

OVERTURE_FACADES = (
    "brick",
    "cement_block",
    "clay",
    "concrete",
    "glass",
    "metal",
    "plaster",
    "plastic",
    "stone",
    "timber",
    "wood",
)
OVERTURE_ROOFS = (
    "concrete",
    "copper",
    "eternit",
    "glass",
    "grass",
    "gravel",
    "metal",
    "plastic",
    "roof_tiles",
    "slate",
    "solar_panels",
    "tar_paper",
    "thatch",
    "wood",
)
SHIPPED_DISTRICTS = ("old-town", "downtown", "industrial", "suburban")
ROOF_SHAPES = ("flat", "gabled", "hipped", "pyramidal")
GLAZING_KINDS = ("none", "punched", "curtain_wall")
DEFAULT_TUNING = "building/fire.json"

_FACADES = ("facades", "facade.json")
_ROOFS = ("roofs", "roof.json")
_DISTRICTS = ("districts", "district.json")


@dataclass(frozen=True)
class BuildingPresets:
    """What an agent can name: shipped names, and the paths of any preset files added."""

    facades: tuple[str, ...]
    roofs: tuple[str, ...]
    districts: tuple[str, ...]


def _listed(
    assets_dir: Path | None, shipped: tuple[str, ...], kind: tuple[str, str]
) -> tuple[str, ...]:
    folder, suffix = kind
    if assets_dir is None:
        return shipped
    present = sorted(p.name for p in (Path(assets_dir) / "building" / folder).glob(f"*.{suffix}"))
    named = [n for n in shipped if f"{n}.{suffix}" in present]
    added = [
        f"building/{folder}/{p}" for p in present if p.removesuffix(f".{suffix}") not in shipped
    ]
    return (*named, *added)


def building_presets(assets_dir: Path | None) -> BuildingPresets:
    """Facade, roof and district names from the preset files present in `assets_dir`; without
    one, the shipped vocabulary."""
    return BuildingPresets(
        facades=_listed(assets_dir, OVERTURE_FACADES, _FACADES),
        roofs=_listed(assets_dir, OVERTURE_ROOFS, _ROOFS),
        districts=_listed(assets_dir, SHIPPED_DISTRICTS, _DISTRICTS),
    )


def _preset(value: object, shipped: tuple[str, ...], kind: tuple[str, str], what: str) -> str:
    folder, suffix = kind
    if not isinstance(value, str) or not value:
        raise ScenarioInvalid(f"{what} must be a name or a path")
    if "/" not in value:
        if value not in shipped:
            raise ScenarioInvalid(f"{what} {value!r} is not a shipped name ({', '.join(shipped)})")
        return value
    pure = PurePosixPath(value)
    prefix = f"building/{folder}/"
    if (
        pure.is_absolute()
        or ".." in pure.parts
        or "" in value.split("/")
        or not value.startswith(prefix)
        or not value.endswith(f".{suffix}")
    ):
        raise ScenarioInvalid(f"{what} {value!r} must be a building/{folder}/*.{suffix} path")
    return value


def _colour(value: object, what: str) -> None:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ScenarioInvalid(f"{what} must be three numbers")
    if any(not 0.0 <= number(v, what) <= 1.0 for v in value):
        raise ScenarioInvalid(f"{what} must be within 0..1")


def _glazing(value: object, building_id: str) -> None:
    if not isinstance(value, dict):
        raise ScenarioInvalid(f"building {building_id}: glazing must be an object")
    if value.get("kind") not in GLAZING_KINDS:
        raise ScenarioInvalid(
            f"building {building_id}: glazing kind {value.get('kind')!r} is not in {GLAZING_KINDS}"
        )
    ratio = value.get("window_ratio")
    if ratio is not None and not 0.0 < number(ratio, "window_ratio") <= 1.0:
        raise ScenarioInvalid(f"building {building_id}: window_ratio must be in (0, 1]")


def _holds(district: Mapping[str, object], x: float, y: float) -> bool:
    centre, size = district.get("position_enu"), district.get("size_m")
    if not (isinstance(centre, list) and isinstance(size, list)):
        return False
    return (
        abs(x - float(centre[0])) <= float(size[0]) / 2
        and abs(y - float(centre[1])) <= float(size[1]) / 2
    )


def _validate_district(district: Mapping[str, object]) -> str:
    district_id = district.get("id")
    if not isinstance(district_id, str) or not district_id:
        raise ScenarioInvalid("every district needs an id")
    _preset(district.get("preset"), SHIPPED_DISTRICTS, _DISTRICTS, f"district {district_id} preset")
    position, size = district.get("position_enu"), district.get("size_m")
    if not isinstance(position, list) or len(position) != 3:
        raise ScenarioInvalid(f"district {district_id}: position_enu must be three numbers")
    if not isinstance(size, list) or len(size) != 2:
        raise ScenarioInvalid(f"district {district_id}: size_m must be (east, north)")
    for value in position:
        number(value, f"district {district_id} position_enu")
    if any(number(v, f"district {district_id} size_m") <= 0 for v in size):
        raise ScenarioInvalid(f"district {district_id}: size_m must be > 0")
    return district_id


def _validate_building(building: Mapping[str, object], districts: list[dict[str, object]]) -> None:
    building_id = str(building.get("id"))
    if building.get("facade") is not None:
        _preset(building["facade"], OVERTURE_FACADES, _FACADES, f"building {building_id} facade")
    if building.get("roof") is not None:
        _preset(building["roof"], OVERTURE_ROOFS, _ROOFS, f"building {building_id} roof")
    shape = building.get("roof_shape")
    if shape is not None and shape not in ROOF_SHAPES:
        raise ScenarioInvalid(
            f"building {building_id}: roof_shape {shape!r} is not one of {ROOF_SHAPES}"
        )
    floors = building.get("floors")
    if floors is not None and (
        isinstance(floors, bool) or not isinstance(floors, int) or floors < 1
    ):
        raise ScenarioInvalid(f"building {building_id}: floors must be a whole number >= 1")
    for key in ("facade_colour", "roof_colour"):
        if building.get(key) is not None:
            _colour(building[key], f"building {building_id} {key}")
    if building.get("glazing") is not None:
        _glazing(building["glazing"], building_id)
    position = building.get("position_enu")
    centre = (float(position[0]), float(position[1])) if isinstance(position, list) else (0.0, 0.0)
    styled = bool(building.get("material")) or (
        building.get("facade") is not None and building.get("roof") is not None
    )
    if not styled and not any(_holds(d, *centre) for d in districts):
        raise ScenarioInvalid(
            f"building {building_id} is in no district: give it a material, or a facade and a roof"
        )


def validate_buildings(manifest: Mapping[str, object]) -> None:
    """Districts, building presets and building fires, as `SceneManifest::from_json` checks them."""
    districts = object_list(manifest, "districts")
    seen: set[str] = set()
    for district in districts:
        district_id = _validate_district(district)
        if district_id in seen:
            raise ScenarioInvalid(f"duplicate district {district_id!r}")
        seen.add(district_id)
    buildings = {
        str(e.get("id")): e
        for e in object_list(manifest, "elements")
        if e.get("kind") == "building"
    }
    for building in buildings.values():
        _validate_building(building, districts)
    taken = {str(e.get("id")) for e in object_list(manifest, "elements")}
    taken |= {str(m.get("id")) for m in object_list(manifest, "models")}
    taken |= {str(f.get("id")) for f in object_list(manifest, "fires")}
    for fire in object_list(manifest, "building_fires"):
        fire_id = fire.get("id")
        if not isinstance(fire_id, str) or not fire_id:
            raise ScenarioInvalid("every building fire needs an id")
        if fire_id in taken:
            raise ScenarioInvalid(f"duplicate id {fire_id!r}")
        taken.add(fire_id)
        target = buildings.get(str(fire.get("building")))
        if target is None:
            raise ScenarioInvalid(f"building fire {fire_id}: no building {fire.get('building')!r}")
        floor = fire.get("floor")
        if isinstance(floor, bool) or not isinstance(floor, int) or floor < 0:
            raise ScenarioInvalid(f"building fire {fire_id}: floor must be a whole number >= 0")
        floors = target.get("floors")
        if isinstance(floors, int) and floor >= floors:
            raise ScenarioInvalid(
                f"building fire {fire_id}: floor {floor} is not below the {floors} floors"
            )
        if number(fire.get("start_s", 0.0), f"building fire {fire_id} start_s") < 0:
            raise ScenarioInvalid(f"building fire {fire_id}: start_s must be >= 0")
        tuning = fire.get("tuning", DEFAULT_TUNING)
        if not isinstance(tuning, str) or not tuning.endswith(".json") or ".." in tuning.split("/"):
            raise ScenarioInvalid(f"building fire {fire_id}: tuning must be a .json path")


def _edited(manifest: Mapping[str, object], key: str, items: list[dict[str, object]]) -> Manifest:
    edited: Manifest = copy.deepcopy(dict(manifest))
    edited[key] = items
    validate_buildings(edited)
    return edited


def set_district(
    manifest: Mapping[str, object],
    district_id: str,
    preset: str,
    *,
    position_enu: tuple[float, float, float],
    size_m: tuple[float, float],
    seed: int = 0,
) -> Manifest:
    """A new manifest with the district `district_id` (replacing one with that id)."""
    district: dict[str, object] = {
        "id": district_id,
        "preset": preset,
        "position_enu": list(position_enu),
        "size_m": list(size_m),
        "seed": seed,
    }
    kept = [d for d in object_list(manifest, "districts") if d.get("id") != district_id]
    return _edited(manifest, "districts", [*kept, district])


def remove_district(manifest: Mapping[str, object], district_id: str) -> Manifest:
    """A new manifest without the district `district_id`."""
    districts = object_list(manifest, "districts")
    if district_id not in [d.get("id") for d in districts]:
        raise ScenarioInvalid(f"no district {district_id!r}")
    return _edited(manifest, "districts", [d for d in districts if d.get("id") != district_id])


def style_building(
    manifest: Mapping[str, object],
    building_id: str,
    *,
    facade: str | None = None,
    roof: str | None = None,
    roof_shape: str | None = None,
    facade_colour: tuple[float, float, float] | None = None,
    roof_colour: tuple[float, float, float] | None = None,
    floors: int | None = None,
    glazing: Mapping[str, object] | None = None,
) -> Manifest:
    """A new manifest in which the building has the given style fields (unset fields stay)."""
    elements = object_list(manifest, "elements")
    found = [e for e in elements if e.get("id") == building_id]
    if not found or found[0].get("kind") != "building":
        raise ScenarioInvalid(f"{building_id!r} is not a building")
    fields: dict[str, object] = {
        "facade": facade,
        "roof": roof,
        "roof_shape": roof_shape,
        "facade_colour": None if facade_colour is None else list(facade_colour),
        "roof_colour": None if roof_colour is None else list(roof_colour),
        "floors": floors,
        "glazing": None if glazing is None else dict(glazing),
    }
    found[0].update({key: value for key, value in fields.items() if value is not None})
    return _edited(manifest, "elements", elements)


def _district_floor_m(district: Mapping[str, object], assets_dir: Path) -> float | None:
    """The district preset's `floor_m`, or None when the station cannot read one (the renderer
    refuses such a preset at load, so no floor count is guessed here)."""
    name = str(district.get("preset"))
    relative = name if "/" in name else f"building/districts/{name}.district.json"
    try:
        preset = json.loads((assets_dir / relative).read_text())
    except (OSError, ValueError):
        return None
    value = preset.get("floor_m") if isinstance(preset, dict) else None
    return float(value) if isinstance(value, int | float) and value > 0 else None


def _check_district_floors(
    manifest: Mapping[str, object], fire_id: str, building_id: str, floor: int, assets_dir: Path
) -> None:
    """Refuse a floor past the count the district gives a building with no `floors` of its own."""
    target = next(
        e
        for e in object_list(manifest, "elements")
        if e.get("kind") == "building" and e.get("id") == building_id
    )
    position, size = target.get("position_enu"), target.get("size_m")
    if target.get("floors") is not None or not (
        isinstance(position, list) and isinstance(size, list) and len(size) == 3
    ):
        return
    district = next(
        (
            d
            for d in reversed(object_list(manifest, "districts"))
            if _holds(d, float(position[0]), float(position[1]))
        ),
        None,
    )
    floor_m = None if district is None else _district_floor_m(district, assets_dir)
    if floor_m is None:
        return
    floors = max(1, math.floor(float(size[2]) / floor_m + 1e-3))
    if floor >= floors:
        raise ScenarioInvalid(
            f"building fire {fire_id}: floor {floor} is not below {building_id}'s {floors} floors"
        )


def add_building_fire(
    manifest: Mapping[str, object],
    fire_id: str,
    *,
    building: str,
    floor: int,
    start_s: float = 0.0,
    assets_dir: Path | None = None,
) -> Manifest:
    """A new manifest with a fire lit in `building` on `floor` at `start_s`. With `assets_dir`, a
    building without `floors` takes the district's count, as the renderer counts them."""
    fire: dict[str, object] = {
        "id": fire_id,
        "building": building,
        "floor": floor,
        "start_s": start_s,
    }
    edited = _edited(manifest, "building_fires", [*object_list(manifest, "building_fires"), fire])
    if assets_dir is not None:
        _check_district_floors(edited, fire_id, building, floor, Path(assets_dir))
    return edited


def remove_building_fire(manifest: Mapping[str, object], fire_id: str) -> Manifest:
    """A new manifest without the building fire `fire_id`."""
    fires = object_list(manifest, "building_fires")
    if fire_id not in [f.get("id") for f in fires]:
        raise ScenarioInvalid(f"no building fire {fire_id!r}")
    return _edited(manifest, "building_fires", [f for f in fires if f.get("id") != fire_id])
