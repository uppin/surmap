"""Read a ``surmap.semantic_map_snapshot.v1`` file.

PR #35's ``surmap.map.snapshot`` is not on this branch. Ask the map only
needs to read the JSON, so the loader lives here and does not write a
snapshot back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from surmap.mapqa.errors import SnapshotError

SCHEMA = "surmap.semantic_map_snapshot.v1"
_MOTIONS = frozenset({"static", "moving", "unknown"})


@dataclass(frozen=True)
class Xyz:
    """Map-frame metres: x east, y north, z up, relative to the origin."""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class MapOrigin:
    t_ns: int
    lat: float
    lon: float
    alt: float
    accuracy_m: float


@dataclass(frozen=True)
class MapObservation:
    t_ns: int
    xyz: Xyz


@dataclass(frozen=True)
class MapFeature:
    id: str
    xyz: Xyz
    lat: float | None
    lon: float | None
    alt: float | None
    label: str
    description: str
    model_id: str
    motion: str
    t_ns: int
    anchor_t_ns: int | None
    offset_ns: int | None
    observations: tuple[MapObservation, ...]
    mask_points: tuple[Xyz, ...] | None


@dataclass(frozen=True)
class MapSnapshot:
    origin: MapOrigin | None
    landmarks: tuple[MapFeature, ...]
    dynamic: tuple[MapFeature, ...]

    def feature(self, feature_id: str) -> MapFeature | None:
        for item in (*self.landmarks, *self.dynamic):
            if item.id == feature_id:
                return item
        return None


def load_snapshot(path: str | Path) -> MapSnapshot:
    """Load one UTF-8 snapshot file."""
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except OSError as exc:
        raise SnapshotError(f"could not read snapshot {file}: {exc}") from exc
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"snapshot {file} is not JSON") from exc
    return parse_snapshot(parsed)


def parse_snapshot(parsed: object) -> MapSnapshot:
    """Parse a decoded JSON value into a snapshot."""
    body = _object(parsed, "snapshot")
    schema = body.get("schema")
    if schema != SCHEMA:
        raise SnapshotError(f"snapshot schema must be {SCHEMA}, got {schema!r}")
    landmarks = _features(body.get("landmarks"), "landmarks")
    dynamic = _features(body.get("dynamic"), "dynamic")
    _reject_duplicate_ids((*landmarks, *dynamic))
    return MapSnapshot(_origin(body.get("origin")), landmarks, dynamic)


def _features(value: object, field: str) -> tuple[MapFeature, ...]:
    if not isinstance(value, list):
        raise SnapshotError(f"{field} must be an array")
    return tuple(_feature(item, f"{field}[{index}]") for index, item in enumerate(value))


def _feature(value: object, where: str) -> MapFeature:
    body = _object(value, where)
    motion = _text(body, "motion", where)
    if motion not in _MOTIONS:
        raise SnapshotError(f"{where}.motion must be static, moving, or unknown")
    return MapFeature(
        _text(body, "id", where),
        _xyz(body.get("xyz"), f"{where}.xyz"),
        _optional_float(body.get("lat"), f"{where}.lat"),
        _optional_float(body.get("lon"), f"{where}.lon"),
        _optional_float(body.get("alt"), f"{where}.alt"),
        _text(body, "label", where),
        _text(body, "description", where),
        _text(body, "model_id", where),
        motion,
        _int(body.get("t_ns"), f"{where}.t_ns"),
        _optional_int(body.get("anchor_t_ns"), f"{where}.anchor_t_ns"),
        _optional_int(body.get("offset_ns"), f"{where}.offset_ns"),
        _observations(body.get("observations"), f"{where}.observations"),
        _mask_points(body.get("mask_points"), f"{where}.mask_points"),
    )


def _origin(value: object) -> MapOrigin | None:
    if value is None:
        return None
    body = _object(value, "origin")
    return MapOrigin(
        _int(body.get("t_ns"), "origin.t_ns"),
        _float(body.get("lat"), "origin.lat"),
        _float(body.get("lon"), "origin.lon"),
        _float(body.get("alt"), "origin.alt"),
        _float(body.get("accuracy_m"), "origin.accuracy_m"),
    )


def _observations(value: object, where: str) -> tuple[MapObservation, ...]:
    if not isinstance(value, list):
        raise SnapshotError(f"{where} must be an array")
    found: list[MapObservation] = []
    for index, item in enumerate(value):
        body = _object(item, f"{where}[{index}]")
        found.append(
            MapObservation(
                _int(body.get("t_ns"), f"{where}[{index}].t_ns"),
                _xyz(body.get("xyz"), f"{where}[{index}].xyz"),
            )
        )
    return tuple(found)


def _mask_points(value: object, where: str) -> tuple[Xyz, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise SnapshotError(f"{where} must be an array or null")
    return tuple(_xyz(item, f"{where}[{index}]") for index, item in enumerate(value))


def _xyz(value: object, where: str) -> Xyz:
    body = _object(value, where)
    return Xyz(
        _float(body.get("x"), f"{where}.x"),
        _float(body.get("y"), f"{where}.y"),
        _float(body.get("z"), f"{where}.z"),
    )


def _reject_duplicate_ids(features: tuple[MapFeature, ...]) -> None:
    seen: set[str] = set()
    for item in features:
        if item.id in seen:
            raise SnapshotError(f"snapshot id {item.id!r} is duplicated")
        seen.add(item.id)


def _object(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SnapshotError(f"{where} must be an object")
    return {str(key): item for key, item in value.items()}


def _text(body: dict[str, object], field: str, where: str) -> str:
    value = body.get(field)
    if not isinstance(value, str):
        raise SnapshotError(f"{where}.{field} must be a string")
    return value


def _float(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SnapshotError(f"{where} must be a number")
    return float(value)


def _optional_float(value: object, where: str) -> float | None:
    if value is None:
        return None
    return _float(value, where)


def _int(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SnapshotError(f"{where} must be an integer")
    return value


def _optional_int(value: object, where: str) -> int | None:
    if value is None:
        return None
    return _int(value, where)
