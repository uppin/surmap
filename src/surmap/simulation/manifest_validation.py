"""Scenario-manifest validation: the rules the renderer applies, mirrored on the station.

Split out of `scenario_manifest` (the manifest edits and presets) for the
repository's file-length gate. `scenario_manifest` re-exports `validate_manifest`
and `ELEMENT_KINDS`, which is where callers have always imported them.
"""

from __future__ import annotations

from collections.abc import Mapping

from surmap.simulation.behaviour_tree import validate_behaviour
from surmap.simulation.building_presets import validate_buildings
from surmap.simulation.fleet_nests import validate_nests
from surmap.simulation.floor_edits import validate_map_floor
from surmap.simulation.manifest_checks import ScenarioInvalid, is_relative_path
from surmap.simulation.manifest_checks import number as _number
from surmap.simulation.manifest_checks import object_list as _list
from surmap.simulation.people import validate_person_look
from surmap.simulation.vehicles import validate_vehicle
from surmap.simulation.water import validate_vessels

ELEMENT_KINDS = (
    "box",
    "collapsed_building",
    "building",
    "person",
    "vegetation",
    "vehicle",
    "drone_nest",
)
COLLIDERS = ("none", "box", "trimesh")


def _materials(manifest: Mapping[str, object]) -> dict[str, dict[str, object]]:
    value = manifest.get("materials", {})
    if not isinstance(value, dict):
        raise ScenarioInvalid("materials must be an object")
    return {str(k): v for k, v in value.items() if isinstance(v, dict)}


def _relative(path: object, what: str) -> str:
    if not isinstance(path, str) or not path:
        raise ScenarioInvalid(f"{what} must be a path")
    if not is_relative_path(path):
        raise ScenarioInvalid(f"{what} {path!r} must stay inside the assets")
    return path


def _file(path: object, what: str, suffix: str) -> str:
    """A relative asset path naming a declarative `suffix` file (`.fx.json`, `.species.json`)."""
    checked = _relative(path, what)
    if not checked.endswith(suffix):
        raise ScenarioInvalid(f"{what} {checked!r} must be a {suffix} file")
    return checked


def _validate_weather(weather: object) -> None:
    if not isinstance(weather, dict):
        raise ScenarioInvalid("weather must be an object")
    if _number(weather.get("rain_mm_h", 0.0), "weather rain_mm_h") < 0:
        raise ScenarioInvalid("weather rain_mm_h must be >= 0")
    if "fog_visibility_m" in weather and weather["fog_visibility_m"] is not None:
        if _number(weather["fog_visibility_m"], "weather fog_visibility_m") <= 0:
            raise ScenarioInvalid("weather fog_visibility_m must be > 0")
    wind = weather.get("wind")
    if not isinstance(wind, dict):
        raise ScenarioInvalid("weather wind must be an object")
    _number(wind.get("from_deg"), "weather wind from_deg")
    for key in ("speed_m_s", "gust_m_s"):
        if _number(wind.get(key, 0.0), f"weather wind {key}") < 0:
            raise ScenarioInvalid(f"weather wind {key} must be >= 0")
    if "rain_fx" in weather:
        _file(weather["rain_fx"], "weather rain_fx", ".fx.json")
    if wind.get("behaviour") is not None:
        validate_behaviour(wind["behaviour"], "wind")


def _validate_fire(fire: Mapping[str, object], seen: set[str]) -> None:
    fire_id = fire.get("id")
    if not isinstance(fire_id, str) or not fire_id:
        raise ScenarioInvalid("every fire needs an id")
    if fire_id in seen:
        raise ScenarioInvalid(f"duplicate id {fire_id!r}")
    seen.add(fire_id)
    ignition = fire.get("ignition_enu")
    if not isinstance(ignition, list) or len(ignition) != 3:
        raise ScenarioInvalid(f"fire {fire_id}: ignition_enu must be three numbers")
    for value in ignition:
        _number(value, f"fire {fire_id} ignition_enu")
    if _number(fire.get("spread_m_s"), f"fire {fire_id} spread_m_s") <= 0:
        raise ScenarioInvalid(f"fire {fire_id}: spread_m_s must be > 0")
    if _number(fire.get("max_radius_m"), f"fire {fire_id} max_radius_m") <= 0:
        raise ScenarioInvalid(f"fire {fire_id}: max_radius_m must be > 0")
    if _number(fire.get("start_s", 0.0), f"fire {fire_id} start_s") < 0:
        raise ScenarioInvalid(f"fire {fire_id}: start_s must be >= 0")
    effects = fire.get("effects", {})
    if not isinstance(effects, dict):
        raise ScenarioInvalid(f"fire {fire_id}: effects must be an object")
    for name, path in effects.items():
        _file(path, f"fire {fire_id} effect {name}", ".fx.json")


def _validate_vegetation(element: Mapping[str, object]) -> None:
    element_id = element.get("id")
    _file(element.get("species"), f"element {element_id}: species", ".species.json")
    size = element.get("size_m")
    if not isinstance(size, list) or len(size) != 2:
        raise ScenarioInvalid(f"element {element_id}: size_m must be (east, north)")
    if any(_number(v, f"element {element_id} size_m") <= 0 for v in size):
        raise ScenarioInvalid(f"element {element_id}: size_m must be > 0")
    density = _number(element.get("density_per_100m2"), f"element {element_id} density")
    if not 0 < density <= 50:
        raise ScenarioInvalid(f"element {element_id}: density_per_100m2 must be in (0, 50]")


def _element_materials(element: Mapping[str, object]) -> list[str]:
    keys: list[object] = []
    kind = element.get("kind")
    if kind == "person":
        keys += [element.get("coat"), element.get("skin")]
    else:
        keys.append(element.get("material"))
    for nested in ("scatter", "windows"):
        inner = element.get(nested)
        if isinstance(inner, dict):
            keys.append(inner.get("material"))
    return [key for key in keys if isinstance(key, str)]


def validate_manifest(manifest: Mapping[str, object]) -> None:
    """Raise `ScenarioInvalid` for anything `SceneManifest::from_json` would refuse."""
    if manifest.get("version") != 1:
        raise ScenarioInvalid(f"unsupported version {manifest.get('version')!r} (must be 1)")
    camera = _relative(manifest.get("camera"), "camera")
    if not camera.endswith(".camera.json"):
        raise ScenarioInvalid(f"camera {camera!r} must be a .camera.json profile")
    if not isinstance(manifest.get("environment"), dict):
        raise ScenarioInvalid("environment must be an object")
    materials = _materials(manifest)
    for key, material in materials.items():
        for field in ("base_color", "normal", "roughness", "arm"):
            if material.get(field) is not None:
                _relative(material.get(field), f"material {key}.{field}")
    seen: set[str] = set()
    scatters = 0
    for element in _list(manifest, "elements"):
        element_id = element.get("id")
        if not isinstance(element_id, str) or not element_id:
            raise ScenarioInvalid("every element needs an id")
        if element.get("kind") not in ELEMENT_KINDS:
            raise ScenarioInvalid(f"element {element_id}: unknown kind {element.get('kind')!r}")
        if element_id in seen:
            raise ScenarioInvalid(f"duplicate id {element_id!r}")
        seen.add(element_id)
        for key in _element_materials(element):
            if key not in materials:
                raise ScenarioInvalid(f"element {element_id}: unknown material {key!r}")
        scatters += isinstance(element.get("scatter"), dict)
        if element.get("kind") == "vegetation":
            _validate_vegetation(element)
        if element.get("kind") == "person":
            validate_person_look(element)
            if element.get("behaviour") is not None:
                validate_behaviour(element["behaviour"], "object")
        if element.get("kind") == "vehicle":
            validate_vehicle(element)
    if scatters > 1:
        raise ScenarioInvalid("at most one element may scatter debris")
    validate_map_floor(manifest)
    if "weather" in manifest:
        _validate_weather(manifest["weather"])
    for model in _list(manifest, "models"):
        model_id = model.get("id")
        if not isinstance(model_id, str) or not model_id:
            raise ScenarioInvalid("every model needs an id")
        if model_id in seen:
            raise ScenarioInvalid(f"duplicate id {model_id!r}")
        seen.add(model_id)
        glb = _relative(model.get("glb"), f"model {model_id}")
        if not glb.endswith((".glb", ".gltf")):
            raise ScenarioInvalid(f"model {model_id}: {glb!r} is not glTF")
        if model.get("collider") not in COLLIDERS:
            raise ScenarioInvalid(f"model {model_id}: collider must be one of {COLLIDERS}")
    for fire in _list(manifest, "fires"):
        _validate_fire(fire, seen)
    validate_buildings(manifest)
    validate_vessels(manifest)
    validate_nests(manifest)
