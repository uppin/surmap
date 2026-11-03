"""Scenario manifests: the Bevy simulation's `scene.json`, edited and validated on the station.

A scenario *is* a scene manifest (examples/bevy-sitl-poc/src/scene_manifest.rs): the station
stores and serves it, the page loads it at runtime. Edits here are pure — they return a new
manifest — and every result is validated by the same rules the renderer applies, so the
station never serves a scene the simulation would refuse.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from surmap.simulation.scenario_store import StoredAsset

Manifest = dict[str, object]
ELEMENT_KINDS = ("box", "collapsed_building", "building", "person", "vegetation")
COLLIDERS = ("none", "box", "trimesh")


class ScenarioInvalid(ValueError):
    """A manifest the renderer would refuse, and why."""


def _list(manifest: Mapping[str, object], key: str) -> list[dict[str, object]]:
    value = manifest.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ScenarioInvalid(f"{key} must be a list of objects")
    return [{str(k): v for k, v in item.items()} for item in value]


def _materials(manifest: Mapping[str, object]) -> dict[str, dict[str, object]]:
    value = manifest.get("materials", {})
    if not isinstance(value, dict):
        raise ScenarioInvalid("materials must be an object")
    return {str(k): v for k, v in value.items() if isinstance(v, dict)}


def _relative(path: object, what: str) -> str:
    if not isinstance(path, str) or not path:
        raise ScenarioInvalid(f"{what} must be a path")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or "" in path.split("/"):
        raise ScenarioInvalid(f"{what} {path!r} must stay inside the assets")
    return path


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioInvalid(f"{what} must be a number")
    return float(value)


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
        if element.get("kind") == "person" and element.get("behaviour") is not None:
            validate_behaviour(element["behaviour"], "object")
    if scatters > 1:
        raise ScenarioInvalid("at most one element may scatter debris")
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


def element_ids(manifest: Mapping[str, object]) -> list[str]:
    """Ids a new element, model or fire must not reuse (a fire shares the namespace)."""
    ids = [str(e.get("id")) for e in _list(manifest, "elements")]
    ids += [str(m.get("id")) for m in _list(manifest, "models")]
    return ids + [str(f.get("id")) for f in _list(manifest, "fires")]


def _with(manifest: Mapping[str, object], key: str, items: Sequence[dict[str, object]]) -> Manifest:
    edited: Manifest = copy.deepcopy(dict(manifest))
    edited[key] = list(items)
    validate_manifest(edited)
    return edited


def add_element(manifest: Mapping[str, object], element: Mapping[str, object]) -> Manifest:
    """A new manifest with `element` appended (ids must stay unique)."""
    element_id = element.get("id")
    if element_id in element_ids(manifest):
        raise ScenarioInvalid(f"duplicate id {element_id!r}")
    return _with(manifest, "elements", [*_list(manifest, "elements"), dict(element)])


def add_model(
    manifest: Mapping[str, object],
    asset: StoredAsset,
    *,
    element_id: str,
    position_enu: tuple[float, float, float],
    yaw_deg: float = 0.0,
    scale: float = 1.0,
    collider: str = "box",
    ground_truth_kind: str | None = None,
) -> Manifest:
    """A new manifest placing a library model."""
    if element_id in element_ids(manifest):
        raise ScenarioInvalid(f"duplicate id {element_id!r}")
    if asset.kind != "model":
        raise ScenarioInvalid(f"{asset.ref} is a {asset.kind}, not a model")
    model: dict[str, object] = {
        "id": element_id,
        "glb": asset.entry,
        "position_enu": list(position_enu),
        "yaw_deg": yaw_deg,
        "scale": scale,
        "collider": collider,
        "ground_truth": ground_truth_kind is not None,
    }
    if ground_truth_kind is not None:
        model["kind"] = ground_truth_kind
    return _with(manifest, "models", [*_list(manifest, "models"), model])


def remove_element(manifest: Mapping[str, object], element_id: str) -> Manifest:
    """A new manifest without the element or model called `element_id`."""
    if element_id not in element_ids(manifest):
        raise ScenarioInvalid(f"no element or model {element_id!r}")
    elements = [e for e in _list(manifest, "elements") if e.get("id") != element_id]
    edited = _with(manifest, "elements", elements)
    return _with(
        edited, "models", [m for m in _list(edited, "models") if m.get("id") != element_id]
    )


def set_weather(
    manifest: Mapping[str, object],
    *,
    rain_mm_h: float,
    fog_visibility_m: float | None,
    wind_from_deg: float,
    wind_speed_m_s: float,
    wind_gust_m_s: float,
) -> Manifest:
    """A new manifest whose weather is the rain, fog and one wind given."""
    edited: Manifest = copy.deepcopy(dict(manifest))
    previous = edited.get("weather")
    weather: dict[str, object] = dict(previous) if isinstance(previous, dict) else {}
    weather["rain_mm_h"] = rain_mm_h
    if fog_visibility_m is None:
        weather.pop("fog_visibility_m", None)
    else:
        weather["fog_visibility_m"] = fog_visibility_m
    weather["wind"] = {
        "from_deg": wind_from_deg,
        "speed_m_s": wind_speed_m_s,
        "gust_m_s": wind_gust_m_s,
    }
    edited["weather"] = weather
    validate_manifest(edited)
    return edited


def add_fire(manifest: Mapping[str, object], fire: Mapping[str, object]) -> Manifest:
    """A new manifest with `fire` appended (its id is unique among elements, models and fires)."""
    fire_id = fire.get("id")
    if fire_id in element_ids(manifest):
        raise ScenarioInvalid(f"duplicate id {fire_id!r}")
    return _with(manifest, "fires", [*_list(manifest, "fires"), dict(fire)])


def remove_fire(manifest: Mapping[str, object], fire_id: str) -> Manifest:
    """A new manifest without the fire called `fire_id`."""
    fires = _list(manifest, "fires")
    if fire_id not in [f.get("id") for f in fires]:
        raise ScenarioInvalid(f"no fire {fire_id!r}")
    return _with(manifest, "fires", [f for f in fires if f.get("id") != fire_id])


# Behaviour trees (changeset § Behaviour-tree JSON): every node kind's fields, and the kinds the
# wind's own tree may use. The renderer applies the same rules (`behaviour.rs`).
_LEAF_FIELDS: dict[str, tuple[str, ...]] = {
    "time_after": ("s",),
    "near_fire": ("within_m",),
    "near_object": ("object", "within_m"),
    "wind_above": ("speed_m_s",),
    "idle": ("s",),
    "move_to": ("enu", "speed_m_s"),
    "follow_path": ("enu", "speed_m_s"),
    "wander": ("radius_m", "speed_m_s", "seed"),
    "flee_from_fire": ("speed_m_s", "clearance_m"),
    "set_wind": ("from_deg", "speed_m_s", "gust_m_s", "over_s"),
}
_NODE_FIELDS: dict[str, tuple[str, ...]] = {
    "sequence": ("children",),
    "selector": ("children",),
    "parallel": ("children", "succeed_on"),
    "repeat": ("child",),
    "invert": ("child",),
    **_LEAF_FIELDS,
}
_OPTIONAL_FIELDS: dict[str, tuple[str, ...]] = {"repeat": ("times",)}
_WIND_KINDS = frozenset(
    {"sequence", "selector", "parallel", "repeat", "invert", "time_after", "idle", "set_wind"}
)


def validate_behaviour(node: object, target: str = "object") -> None:
    """Raise `ScenarioInvalid` unless `node` is a tree `target` ("object" or "wind") can run."""
    _check_node(node, target, set())


def _check_node(node: object, target: str, ids: set[str]) -> None:
    if not isinstance(node, dict):
        raise ScenarioInvalid("a behaviour node must be an object")
    fields = {str(k): v for k, v in node.items()}
    kind = fields.get("node")
    if not isinstance(kind, str) or kind not in _NODE_FIELDS:
        raise ScenarioInvalid(f"unknown node kind {kind!r}")
    required = _NODE_FIELDS[kind]
    allowed = {"node", "id", *required, *_OPTIONAL_FIELDS.get(kind, ())}
    for field in fields:
        if field not in allowed:
            raise ScenarioInvalid(f"{kind}: unknown field {field!r}")
    for field in required:
        if field not in fields:
            raise ScenarioInvalid(f"{kind}: missing {field!r}")
    if "id" in fields:
        _claim_node_id(fields["id"], ids)
    _check_target(kind, target)
    _check_values(kind, fields, target, ids)


def _claim_node_id(value: object, ids: set[str]) -> None:
    if not isinstance(value, str) or not value:
        raise ScenarioInvalid("a node id must be a non-empty string")
    if value in ids:
        raise ScenarioInvalid(f"duplicate node id {value!r}")
    ids.add(value)


def _check_target(kind: str, target: str) -> None:
    if target == "object" and kind == "set_wind":
        raise ScenarioInvalid("set_wind drives the wind, so only the wind's own tree may use it")
    if target == "wind" and kind not in _WIND_KINDS:
        raise ScenarioInvalid(
            f"{kind} is not allowed in the wind's tree: it may use only composites, "
            "decorators, time_after, idle and set_wind"
        )


def _check_values(kind: str, fields: Mapping[str, object], target: str, ids: set[str]) -> None:
    if kind in ("sequence", "selector", "parallel"):
        children = fields["children"]
        if not isinstance(children, list) or not children:
            raise ScenarioInvalid(f"{kind}: children must be a non-empty list")
        if kind == "parallel" and fields["succeed_on"] not in ("all", "one"):
            raise ScenarioInvalid("parallel: succeed_on must be 'all' or 'one'")
        for child in children:
            _check_node(child, target, ids)
    elif kind in ("repeat", "invert"):
        times = fields.get("times")
        if times is not None and (
            not isinstance(times, int) or isinstance(times, bool) or times < 1
        ):
            raise ScenarioInvalid("repeat: times must be a whole number >= 1")
        _check_node(fields["child"], target, ids)
    elif kind == "near_object":
        _claim_object(fields["object"])
        _bound(fields, kind, "within_m", low=0.0, strict=True)
    elif kind == "near_fire":
        _bound(fields, kind, "within_m", low=0.0, strict=True)
    elif kind == "time_after":
        _bound(fields, kind, "s", low=0.0, strict=False)
    elif kind == "idle":
        _bound(fields, kind, "s", low=0.0, strict=True)
    elif kind == "wind_above":
        _bound(fields, kind, "speed_m_s", low=0.0, strict=False)
    elif kind in ("move_to", "follow_path"):
        _check_path(kind, fields)
        _bound(fields, kind, "speed_m_s", low=0.0, strict=True)
    elif kind == "wander":
        _bound(fields, kind, "radius_m", low=0.0, strict=True)
        _bound(fields, kind, "speed_m_s", low=0.0, strict=True)
        seed = fields["seed"]
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise ScenarioInvalid("wander: seed must be a whole number >= 0")
    elif kind == "flee_from_fire":
        _bound(fields, kind, "speed_m_s", low=0.0, strict=True)
        _bound(fields, kind, "clearance_m", low=0.0, strict=False)
    elif kind == "set_wind":
        _number(fields["from_deg"], f"{kind}: from_deg")
        _bound(fields, kind, "speed_m_s", low=0.0, strict=False)
        _bound(fields, kind, "gust_m_s", low=0.0, strict=False)
        _bound(fields, kind, "over_s", low=0.0, strict=True)


def _claim_object(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ScenarioInvalid("near_object: object must name the other body")


def _bound(
    fields: Mapping[str, object], kind: str, field: str, *, low: float, strict: bool
) -> None:
    value = _number(fields[field], f"{kind}: {field}")
    if value < low or (strict and value == low):
        raise ScenarioInvalid(f"{kind}: {field} must be {'> ' if strict else '>= '}{low:g}")


def _check_path(kind: str, fields: Mapping[str, object]) -> None:
    enu = fields["enu"]
    if kind == "move_to":
        _check_point(enu, kind)
        return
    if not isinstance(enu, list) or not enu:
        raise ScenarioInvalid(f"{kind}: enu must be a non-empty list of [east, north] points")
    for point in enu:
        _check_point(point, kind)


def _check_point(point: object, kind: str) -> None:
    if not isinstance(point, list) or len(point) != 2:
        raise ScenarioInvalid(f"{kind}: enu must be [east, north]")
    for value in point:
        _number(value, f"{kind}: enu")


def _resolve_target(manifest: Mapping[str, object], target_id: str) -> str:
    """Whether a behaviour tree can be set on `target_id` here: "wind" or "person", else refused."""
    if target_id == "wind":
        if not isinstance(manifest.get("weather"), dict):
            raise ScenarioInvalid(
                "the wind takes a behaviour tree only once the scenario has weather"
            )
        return "wind"
    for element in _list(manifest, "elements"):
        if element.get("id") == target_id:
            if element.get("kind") == "person":
                return "person"
            raise ScenarioInvalid(
                f"{target_id!r} is a {element.get('kind')}: "
                "only people and the wind take behaviour trees"
            )
    raise ScenarioInvalid(f"no person or wind {target_id!r} in this scenario")


def _person_of(manifest: Mapping[str, object], target_id: str) -> dict[str, object]:
    """The person element called `target_id` (checked by `_resolve_target` first)."""
    for element in _list(manifest, "elements"):
        if element.get("id") == target_id:
            return element
    raise ScenarioInvalid(f"no person {target_id!r} in this scenario")


def behaviour_of(manifest: Mapping[str, object], target_id: str) -> Manifest | None:
    """The behaviour tree of a person or of the wind, or None when it has none."""
    if _resolve_target(manifest, target_id) == "wind":
        tree = _wind_of(manifest).get("behaviour")
    else:
        tree = _person_of(manifest, target_id).get("behaviour")
    return copy.deepcopy(dict(tree)) if isinstance(tree, dict) else None


def _wind_of(manifest: Mapping[str, object]) -> dict[str, object]:
    weather = manifest.get("weather")
    wind = weather.get("wind") if isinstance(weather, dict) else None
    return {str(k): v for k, v in wind.items()} if isinstance(wind, dict) else {}


def set_behaviour(
    manifest: Mapping[str, object], target_id: str, tree: Mapping[str, object]
) -> Manifest:
    """A new manifest in which the person (or the wind) runs `tree`, refused unless it is valid."""
    kind = _resolve_target(manifest, target_id)
    validate_behaviour(tree, "wind" if kind == "wind" else "object")
    edited: Manifest = copy.deepcopy(dict(manifest))
    holders: list[object]
    if kind == "wind":
        weather = edited.get("weather")
        holders = [weather.get("wind")] if isinstance(weather, dict) else []
    else:
        elements = edited.get("elements")
        holders = (
            [e for e in elements if isinstance(e, dict) and e.get("id") == target_id]
            if isinstance(elements, list)
            else []
        )
    for holder in holders:
        if isinstance(holder, dict):
            holder["behaviour"] = copy.deepcopy(dict(tree))
    validate_manifest(edited)
    return edited


def update_behaviour_node(
    manifest: Mapping[str, object],
    target_id: str,
    node_id: str,
    node: Mapping[str, object],
) -> Manifest:
    """A new manifest whose tree has the node `node_id` replaced by `node` and its subtree."""
    tree = behaviour_of(manifest, target_id)
    if tree is None:
        raise ScenarioInvalid(f"{target_id!r} has no behaviour tree to update")
    replaced = _replace_node(tree, node_id, node)
    if replaced is None:
        raise ScenarioInvalid(f"no node {node_id!r} in the behaviour tree of {target_id!r}")
    return set_behaviour(manifest, target_id, replaced)


def _replace_node(
    tree: Mapping[str, object], node_id: str, node: Mapping[str, object]
) -> dict[str, object] | None:
    """The tree with the node whose id is `node_id` replaced, or None when no node has that id."""
    if tree.get("id") == node_id:
        return copy.deepcopy(dict(node))
    for key in ("children", "child"):
        value = tree.get(key)
        if isinstance(value, list):
            for index, child in enumerate(value):
                found = _replace_node(child, node_id, node) if isinstance(child, dict) else None
                if found is not None:
                    return {**tree, key: [*value[:index], found, *value[index + 1 :]]}
        elif isinstance(value, dict):
            found = _replace_node(value, node_id, node)
            if found is not None:
                return {**tree, key: found}
    return None


def _stand(
    stand_id: str,
    species: str,
    centre: tuple[float, float],
    size: tuple[float, float],
    **plan: object,
) -> dict[str, object]:
    return {
        "kind": "vegetation",
        "id": stand_id,
        "species": f"species/{species}.species.json",
        "position_enu": [centre[0], centre[1], 0.0],
        "size_m": list(size),
        **plan,
    }


def _wildfire_edge(lot: Manifest) -> Manifest:
    """The empty lot with two pine stands in dry grass, a 6 m/s westerly and a fire upwind."""
    edge = add_element(
        lot,
        _stand("grass", "dry_grass", (0.0, 60.0), (150.0, 80.0), density_per_100m2=30.0, seed=7),
    )
    edge = add_element(
        edge,
        _stand("pines-west", "pine", (-40.0, 60.0), (40.0, 60.0), density_per_100m2=3.0, seed=11),
    )
    edge = add_element(
        edge,
        _stand("pines-east", "pine", (35.0, 55.0), (30.0, 40.0), density_per_100m2=3.0, seed=23),
    )
    edge = set_weather(
        edge,
        rain_mm_h=0.0,
        fog_visibility_m=None,
        wind_from_deg=270.0,
        wind_speed_m_s=6.0,
        wind_gust_m_s=2.0,
    )
    return add_fire(
        edge,
        {
            "id": "front-1",
            "ignition_enu": [-58.0, 60.0, 0.0],
            "start_s": 2.0,
            "spread_m_s": 0.15,
            "max_radius_m": 35.0,
            "smoke": True,
        },
    )


def _flood_street(block: Manifest) -> Manifest:
    """The earthquake block in 8 mm/h rain and 250 m fog, with a calm 2 m/s wind."""
    return set_weather(
        block,
        rain_mm_h=8.0,
        fog_visibility_m=250.0,
        wind_from_deg=250.0,
        wind_speed_m_s=2.0,
        wind_gust_m_s=0.0,
    )


def _evacuee(seed: int) -> dict[str, object]:
    """Flee the fire when it is within 20 m, until 30 m clear of it; otherwise wander. The tree
    repeats, so an evacuee wanders again once clear and flees again if the front comes back."""
    escape: dict[str, object] = {
        "node": "sequence",
        "id": "escape",
        "children": [
            {"node": "near_fire", "id": "smell-fire", "within_m": 20.0},
            {"node": "flee_from_fire", "id": "run", "speed_m_s": 3.0, "clearance_m": 30.0},
        ],
    }
    mill_about: dict[str, object] = {
        "node": "wander",
        "id": "mill-about",
        "radius_m": 6.0,
        "speed_m_s": 0.8,
        "seed": seed,
    }
    selector: dict[str, object] = {
        "node": "selector",
        "id": "root",
        "children": [escape, mill_about],
    }
    return {"node": "repeat", "child": selector}


# The wind backs and builds 20 s in, then veers to 300° at 10 m/s with 3 m/s gusts over 30 s.
EVACUATION_WIND: dict[str, object] = {
    "node": "sequence",
    "id": "veer",
    "children": [
        {"node": "idle", "id": "calm", "s": 20.0},
        {
            "node": "set_wind",
            "id": "veer-to-300",
            "from_deg": 300.0,
            "speed_m_s": 10.0,
            "gust_m_s": 3.0,
            "over_s": 30.0,
        },
    ],
}


def _evacuation(edge: Manifest) -> Manifest:
    """The wildfire edge with three people at the pines' downwind edge, each fleeing the fire or
    wandering, and the wind driven by `EVACUATION_WIND`."""
    scenario = edge
    for seed, (person_id, north) in enumerate(
        (("evacuee-1", 52.0), ("evacuee-2", 60.0), ("evacuee-3", 68.0)), start=7
    ):
        person = {
            "kind": "person",
            "id": person_id,
            "position_enu": [-16.0, north, 0.0],
            "coat": "coat_orange",
            "skin": "skin",
        }
        scenario = add_element(scenario, person)
        scenario = set_behaviour(scenario, person_id, _evacuee(seed))
    return set_behaviour(scenario, "wind", EVACUATION_WIND)


def load_presets(assets_dir: Path) -> dict[str, Manifest]:
    """`earthquake-block` (the shipped scene), `empty-lot` (its rig, sky and bare ground),
    `wildfire-edge` and `flood-street` built from them, and `wildfire-evacuation`: the edge with
    people and a veering wind."""
    block: Manifest = json.loads((Path(assets_dir) / "scene.json").read_text(encoding="utf-8"))
    materials = _materials(block)
    lot: Manifest = {
        "version": 1,
        "camera": block["camera"],
        "environment": copy.deepcopy(block["environment"]),
        "materials": {k: copy.deepcopy(v) for k, v in materials.items()},
        "elements": [
            {
                "kind": "box",
                "id": "ground",
                "material": "ground",
                "size_m": [200.0, 200.0, 0.2],
                "position_enu": [0.0, 0.0, -0.2],
                "collider": True,
            }
        ],
        "models": [],
    }
    for manifest in (block, lot):
        validate_manifest(manifest)
    edge = _wildfire_edge(lot)
    return {
        "earthquake-block": block,
        "empty-lot": lot,
        "wildfire-edge": edge,
        "wildfire-evacuation": _evacuation(edge),
        "flood-street": _flood_street(block),
    }
