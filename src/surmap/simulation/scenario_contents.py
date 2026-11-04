"""What a scenario manifest contains, in the agent's terms: one item per placed thing, and the
weather in one line. `describe_scenario` serves it, so the agent can learn a scene it did not
build without reading the raw manifest."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from surmap.simulation.manifest_checks import object_list

Item = Mapping[str, object]


@dataclass(frozen=True)
class SceneItem:
    id: str
    kind: str
    """An element kind, or `model`, `fire`, `building_fire`, `district`."""
    detail: str
    position_enu: tuple[float, float, float] | None
    has_behaviour: bool


def scene_items(manifest: Mapping[str, object]) -> list[SceneItem]:
    """Every element, model, fire, building fire and district, in manifest order by section."""
    items = [
        _item(e, str(e.get("kind")), _ELEMENT_DETAIL) for e in object_list(manifest, "elements")
    ]
    items += [_item(m, "model", _model) for m in object_list(manifest, "models")]
    items += [_item(f, "fire", _fire) for f in object_list(manifest, "fires")]
    items += [
        _item(f, "building_fire", _building_fire) for f in object_list(manifest, "building_fires")
    ]
    items += [_item(d, "district", _district) for d in object_list(manifest, "districts")]
    return items


def weather_line(manifest: Mapping[str, object]) -> str:
    """e.g. `rain 8 mm/h, fog to 250 m, wind from 250° at 2 m/s`; `clear and calm` when none."""
    weather = manifest.get("weather")
    if not isinstance(weather, dict):
        return "clear and calm"
    parts: list[str] = []
    rain = weather.get("rain_mm_h")
    if _positive(rain):
        parts.append(f"rain {_n(rain)} mm/h")
    fog = weather.get("fog_visibility_m")
    if _positive(fog):
        parts.append(f"fog to {_n(fog)} m")
    wind = weather.get("wind")
    if isinstance(wind, dict) and _positive(wind.get("speed_m_s")):
        line = f"wind from {_n(wind.get('from_deg'))}° at {_n(wind.get('speed_m_s'))} m/s"
        if _positive(wind.get("gust_m_s")):
            line += f", gusting {_n(wind.get('gust_m_s'))}"
        if isinstance(wind.get("behaviour"), dict):
            line += " (a behaviour drives it)"
        parts.append(line)
    return ", ".join(parts) or "clear and calm"


def _item(
    raw: Item, kind: str, detail: Callable[[Item], str] | Mapping[str, Callable[[Item], str]]
) -> SceneItem:
    describe = detail.get(kind, _material) if isinstance(detail, Mapping) else detail
    return SceneItem(
        id=str(raw.get("id")),
        kind=kind,
        detail=describe(raw),
        position_enu=_position(raw.get("position_enu", raw.get("ignition_enu"))),
        has_behaviour=isinstance(raw.get("behaviour"), dict),
    )


def _position(value: object) -> tuple[float, float, float] | None:
    if not isinstance(value, Sequence) or isinstance(value, str) or len(value) != 3:
        return None
    east, north, up = (_number(v) for v in value)
    if east is None or north is None or up is None:
        return None
    return east, north, up


def _material(raw: Item) -> str:
    material = raw.get("material")
    return str(material) if isinstance(material, str) else ""


def _building(raw: Item) -> str:
    parts = [_size(raw.get("size_m"))]
    if _is_number(raw.get("floors")):
        parts.append(f"{_n(raw.get('floors'))} floors")
    for key in ("facade", "material"):
        if isinstance(raw.get(key), str):
            parts.append(str(raw.get(key)))
            break
    return ", ".join(p for p in parts if p)


def _person(raw: Item) -> str:
    pose = raw.get("pose")
    return str(pose) if isinstance(pose, str) and pose else "standing"


def _vehicle(raw: Item) -> str:
    return str(raw.get("class", ""))


def _vegetation(raw: Item) -> str:
    species = str(raw.get("species", "")).rsplit("/", 1)[-1].removesuffix(".species.json")
    return ", ".join(p for p in (species, _size(raw.get("size_m"))) if p)


def _nest(raw: Item) -> str:
    drones = raw.get("drones")
    return f"{_n(drones)} drones" if _is_number(drones) else ""


def _model(raw: Item) -> str:
    kind = raw.get("kind")
    glb = str(raw.get("glb", ""))
    return f"{kind}, {glb}" if isinstance(kind, str) else glb


def _fire(raw: Item) -> str:
    return (
        f"spreads {_n(raw.get('spread_m_s'))} m/s to {_n(raw.get('max_radius_m'))} m, "
        f"from {_n(raw.get('start_s', 0))} s"
    )


def _building_fire(raw: Item) -> str:
    return (
        f"on {raw.get('building')}, floor {_n(raw.get('floor'))}, "
        f"from {_n(raw.get('start_s', 0))} s"
    )


def _district(raw: Item) -> str:
    return ", ".join(p for p in (str(raw.get("preset", "")), _size(raw.get("size_m"))) if p)


_ELEMENT_DETAIL: Mapping[str, Callable[[Item], str]] = {
    "building": _building,
    "person": _person,
    "vehicle": _vehicle,
    "vegetation": _vegetation,
    "drone_nest": _nest,
}


def _size(value: object) -> str:
    if isinstance(value, Sequence) and value and all(_is_number(v) for v in value):
        return " × ".join(_n(v) for v in value) + " m"
    return ""


def _is_number(value: object) -> bool:
    return _number(value) is not None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _positive(value: object) -> bool:
    number = _number(value)
    return number is not None and number > 0


def _n(value: object) -> str:
    """A number without a trailing `.0`."""
    number = _number(value)
    if number is None:
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"
