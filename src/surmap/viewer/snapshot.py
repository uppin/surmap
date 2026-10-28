"""Read a `surmap.semantic_map_snapshot.v1` file.

The schema lives in PR #35 (`docs/semantic-map-snapshot.md`). This
reader accepts that file and does not import the unmerged writer.
"""

from __future__ import annotations

import json
from pathlib import Path

from surmap.types import Vec3
from surmap.viewer.model import SCHEMA, Observation, Origin, SemanticMapSnapshot, Track


def read_snapshot(path: Path) -> SemanticMapSnapshot:
    """Load one snapshot. Raises `ValueError` when the file is not v1."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a JSON object")
    document = {str(key): value for key, value in raw.items()}
    schema = document.get("schema")
    if schema != SCHEMA:
        raise ValueError(f"unsupported snapshot schema {schema!r}; expected {SCHEMA}")
    landmarks = _tracks(document.get("landmarks"), "landmarks")
    dynamic = _tracks(document.get("dynamic"), "dynamic")
    ids = [track.id for track in landmarks + dynamic]
    if len(ids) != len(set(ids)):
        raise ValueError("snapshot track ids must be unique across landmarks and dynamic")
    return SemanticMapSnapshot(
        origin=_origin(document.get("origin")),
        landmarks=landmarks,
        dynamic=dynamic,
    )


def _origin(value: object) -> Origin | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("origin must be an object or null")
    fields = {str(key): item for key, item in value.items()}
    return Origin(
        t_ns=_int(fields.get("t_ns"), "origin.t_ns"),
        lat=_float(fields.get("lat"), "origin.lat"),
        lon=_float(fields.get("lon"), "origin.lon"),
        alt=_float(fields.get("alt"), "origin.alt"),
        accuracy_m=_float(fields.get("accuracy_m"), "origin.accuracy_m"),
    )


def _tracks(value: object, layer: str) -> tuple[Track, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{layer} must be an array")
    tracks = []
    for index, item in enumerate(value):
        tracks.append(_track(item, f"{layer}[{index}]", layer))
    return tuple(tracks)


def _track(value: object, field: str, layer: str) -> Track:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    fields = {str(key): item for key, item in value.items()}
    motion = fields.get("motion")
    if not isinstance(motion, str) or not motion:
        raise ValueError(f"{field}.motion must be a string")
    if layer == "landmarks" and motion not in ("static", "unknown"):
        raise ValueError(f"{field}.motion must be static or unknown")
    if layer == "dynamic" and motion != "moving":
        raise ValueError(f"{field}.motion must be moving")
    track_id = fields.get("id")
    if not isinstance(track_id, str) or not track_id:
        raise ValueError(f"{field}.id must be a string")
    observations = _observations(fields.get("observations"), f"{field}.observations")
    if not observations:
        raise ValueError(f"{field}.observations must not be empty")
    return Track(
        id=track_id,
        xyz=_xyz(fields.get("xyz"), f"{field}.xyz"),
        lat=_optional_float(fields.get("lat"), f"{field}.lat"),
        lon=_optional_float(fields.get("lon"), f"{field}.lon"),
        alt=_optional_float(fields.get("alt"), f"{field}.alt"),
        label=_text(fields.get("label"), f"{field}.label"),
        description=_text(fields.get("description"), f"{field}.description"),
        model_id=_text(fields.get("model_id"), f"{field}.model_id"),
        motion=motion,
        t_ns=_int(fields.get("t_ns"), f"{field}.t_ns"),
        anchor_t_ns=_optional_int(fields.get("anchor_t_ns"), f"{field}.anchor_t_ns"),
        offset_ns=_optional_int(fields.get("offset_ns"), f"{field}.offset_ns"),
        observations=observations,
        mask_points=_mask(fields.get("mask_points"), f"{field}.mask_points"),
        layer=layer,
    )


def _observations(value: object, field: str) -> tuple[Observation, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    observations = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        fields = {str(key): entry for key, entry in item.items()}
        observations.append(
            Observation(
                t_ns=_int(fields.get("t_ns"), f"{field}[{index}].t_ns"),
                xyz=_xyz(fields.get("xyz"), f"{field}[{index}].xyz"),
            )
        )
    return tuple(observations)


def _mask(value: object, field: str) -> tuple[Vec3, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array or null")
    return tuple(_xyz(item, f"{field}[{index}]") for index, item in enumerate(value))


def _xyz(value: object, field: str) -> Vec3:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object with x, y, z")
    fields = {str(key): item for key, item in value.items()}
    return Vec3(
        _float(fields.get("x"), f"{field}.x"),
        _float(fields.get("y"), f"{field}.y"),
        _float(fields.get("z"), f"{field}.z"),
    )


def _text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


def _int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _int(value, field)


def _float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number")
    return float(value)


def _optional_float(value: object, field: str) -> float | None:
    if value is None:
        return None
    return _float(value, field)
