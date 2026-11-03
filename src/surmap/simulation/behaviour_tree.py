"""Behaviour trees in a scenario (bevy-simulation.md § Behaviour trees; renderer: `behaviour.rs`).

The node rules per target (a person, or the wind), reading a target's tree, replacing a node by
its id, and the trees of the `wildfire-evacuation` preset. Pure: the manifest edits that store a
tree live in `scenario_manifest`.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

from surmap.simulation.manifest_checks import Manifest, ScenarioInvalid, number, object_list

# Every node kind's fields, and the kinds the wind's own tree may use.
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
        number(fields["from_deg"], f"{kind}: from_deg")
        _bound(fields, kind, "speed_m_s", low=0.0, strict=False)
        _bound(fields, kind, "gust_m_s", low=0.0, strict=False)
        _bound(fields, kind, "over_s", low=0.0, strict=True)


def _claim_object(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ScenarioInvalid("near_object: object must name the other body")


def _bound(
    fields: Mapping[str, object], kind: str, field: str, *, low: float, strict: bool
) -> None:
    value = number(fields[field], f"{kind}: {field}")
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
        number(value, f"{kind}: enu")


def resolve_target(manifest: Mapping[str, object], target_id: str) -> str:
    """Whether a behaviour tree can be set on `target_id` here: "wind" or "person", else refused."""
    if target_id == "wind":
        if not isinstance(manifest.get("weather"), dict):
            raise ScenarioInvalid(
                "the wind takes a behaviour tree only once the scenario has weather"
            )
        return "wind"
    for element in object_list(manifest, "elements"):
        if element.get("id") == target_id:
            if element.get("kind") == "person":
                return "person"
            raise ScenarioInvalid(
                f"{target_id!r} is a {element.get('kind')}: "
                "only people and the wind take behaviour trees"
            )
    raise ScenarioInvalid(f"no person or wind {target_id!r} in this scenario")


def _person_of(manifest: Mapping[str, object], target_id: str) -> dict[str, object]:
    """The person element called `target_id` (checked by `resolve_target` first)."""
    for element in object_list(manifest, "elements"):
        if element.get("id") == target_id:
            return element
    raise ScenarioInvalid(f"no person {target_id!r} in this scenario")


def behaviour_of(manifest: Mapping[str, object], target_id: str) -> Manifest | None:
    """The behaviour tree of a person or of the wind, or None when it has none."""
    if resolve_target(manifest, target_id) == "wind":
        tree = _wind_of(manifest).get("behaviour")
    else:
        tree = _person_of(manifest, target_id).get("behaviour")
    return copy.deepcopy(dict(tree)) if isinstance(tree, dict) else None


def _wind_of(manifest: Mapping[str, object]) -> dict[str, object]:
    weather = manifest.get("weather")
    wind = weather.get("wind") if isinstance(weather, dict) else None
    return {str(k): v for k, v in wind.items()} if isinstance(wind, dict) else {}


def replace_node(
    tree: Mapping[str, object], node_id: str, node: Mapping[str, object]
) -> dict[str, object] | None:
    """The tree with the node whose id is `node_id` replaced, or None when no node has that id."""
    if tree.get("id") == node_id:
        return copy.deepcopy(dict(node))
    for key in ("children", "child"):
        value = tree.get(key)
        if isinstance(value, list):
            for index, child in enumerate(value):
                found = replace_node(child, node_id, node) if isinstance(child, dict) else None
                if found is not None:
                    return {**tree, key: [*value[:index], found, *value[index + 1 :]]}
        elif isinstance(value, dict):
            found = replace_node(value, node_id, node)
            if found is not None:
                return {**tree, key: found}
    return None


def evacuee_tree(seed: int) -> dict[str, object]:
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


# The wind holds for 20 s, then veers to 300° and builds to 10 m/s with 3 m/s gusts over 30 s.
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
