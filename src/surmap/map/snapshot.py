"""GPS-anchored semantic map snapshot.

One UTF-8 JSON file is the export until a GeoJSON decision is made.
Map xyz is local ENU metres from the earliest GPS fix: x east, y north,
z up. A landmark's lat/lon/alt is that origin plus its xyz. The nearest
fix in time is recorded separately as ``offset_ns`` and is not the
position. Moving tracks stay in ``dynamic`` and are not copied onto
landmarks. See ``docs/semantic-map-snapshot.md``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import cos, radians
from pathlib import Path

from surmap.motion import classify_motion
from surmap.types import GpsCheckpoint, Motion, ObjectTrack3D, Vec3

SNAPSHOT_SCHEMA = "surmap.semantic_map_snapshot.v1"

# One degree of latitude. Longitude is this times cos(origin latitude).
# Consumer GPS is coarser than this approximation; precise geometry stays in xyz.
_METRES_PER_DEGREE_LATITUDE = 111_320.0


@dataclass(frozen=True)
class MapOrigin:
    """Earliest GPS fix. Defines the ENU frame for the whole snapshot."""

    t_ns: int
    lat: float
    lon: float
    alt: float
    accuracy_m: float


@dataclass(frozen=True)
class MapObservation:
    """One sighting of a track, in the map frame."""

    t_ns: int
    xyz: Vec3


@dataclass(frozen=True)
class MapLandmark:
    """One track in the snapshot, static or moving.

    ``id`` is the decimal ``track_id``. It is stable for that track inside
    a session. ``mask_points`` is ``None`` when the caller did not attach a
    cloud, and a (possibly empty) tuple when it did.
    """

    id: str
    xyz: Vec3
    lat: float | None
    lon: float | None
    alt: float | None
    label: str
    description: str
    model_id: str
    motion: Motion
    offset_ns: int | None
    anchor_t_ns: int | None
    t_ns: int
    observations: tuple[MapObservation, ...]
    mask_points: tuple[Vec3, ...] | None = None


@dataclass(frozen=True)
class MetaCallRecord:
    """One hosted Meta call: role, model id, and elapsed seconds."""

    role: str
    model_id: str
    elapsed_s: float
    confidences: tuple[float | None, ...] = ()


@dataclass(frozen=True)
class SemanticMapSnapshot:
    """Layered semantic map. ``landmarks`` and ``dynamic`` are never merged."""

    schema: str
    origin: MapOrigin | None
    landmarks: tuple[MapLandmark, ...]
    dynamic: tuple[MapLandmark, ...]
    meta_calls: tuple[MetaCallRecord, ...] = ()


def build_snapshot(
    tracks: Sequence[ObjectTrack3D],
    checkpoints: Sequence[GpsCheckpoint],
    *,
    descriptions: Mapping[int, str] | None = None,
    model_ids: Mapping[int, str] | None = None,
    mask_points: Mapping[int, Sequence[Vec3]] | None = None,
) -> SemanticMapSnapshot:
    """Classify tracks and anchor each one to the nearest GPS fix by time."""
    _reject_duplicate_track_ids(tracks)
    label_text = descriptions or {}
    models = model_ids or {}
    clouds = mask_points
    origin = _origin(checkpoints)
    landmarks: list[MapLandmark] = []
    dynamic: list[MapLandmark] = []
    for track in tracks:
        if not track.observations:
            continue
        landmark = _landmark(track, checkpoints, origin, label_text, models, clouds)
        if landmark.motion is Motion.MOVING:
            dynamic.append(landmark)
        else:
            landmarks.append(landmark)
    landmarks.sort(key=_by_track_id)
    dynamic.sort(key=_by_track_id)
    return SemanticMapSnapshot(SNAPSHOT_SCHEMA, origin, tuple(landmarks), tuple(dynamic))


def write_snapshot(snapshot: SemanticMapSnapshot, destination: Path) -> None:
    """Write ``snapshot`` as UTF-8 JSON."""
    text = json.dumps(_snapshot_json(snapshot), indent=2, ensure_ascii=False) + "\n"
    destination.write_text(text, encoding="utf-8")


def read_snapshot(path: Path) -> SemanticMapSnapshot:
    """Read a snapshot written by ``write_snapshot``."""
    return _parse_snapshot(json.loads(path.read_text(encoding="utf-8")))


def _reject_duplicate_track_ids(tracks: Sequence[ObjectTrack3D]) -> None:
    seen: set[int] = set()
    for track in tracks:
        if track.track_id in seen:
            raise ValueError(f"duplicate track id {track.track_id}")
        seen.add(track.track_id)


def _by_track_id(landmark: MapLandmark) -> int:
    return int(landmark.id)


def _origin(checkpoints: Sequence[GpsCheckpoint]) -> MapOrigin | None:
    if not checkpoints:
        return None
    earliest = min(enumerate(checkpoints), key=lambda item: (item[1].t_ns, item[0]))[1]
    return MapOrigin(
        earliest.t_ns,
        earliest.lat,
        earliest.lon,
        earliest.alt,
        earliest.accuracy_m,
    )


def _nearest(t_ns: int, checkpoints: Sequence[GpsCheckpoint]) -> GpsCheckpoint | None:
    if not checkpoints:
        return None
    return min(
        enumerate(checkpoints),
        key=lambda item: (abs(item[1].t_ns - t_ns), item[1].t_ns, item[0]),
    )[1]


def _enu_to_wgs84(xyz: Vec3, origin: MapOrigin) -> tuple[float, float, float]:
    lat = origin.lat + xyz.y / _METRES_PER_DEGREE_LATITUDE
    metres_per_degree_lon = _METRES_PER_DEGREE_LATITUDE * cos(radians(origin.lat))
    lon = origin.lon + xyz.x / metres_per_degree_lon
    return lat, lon, origin.alt + xyz.z


def _landmark(
    track: ObjectTrack3D,
    checkpoints: Sequence[GpsCheckpoint],
    origin: MapOrigin | None,
    descriptions: Mapping[int, str],
    model_ids: Mapping[int, str],
    mask_points: Mapping[int, Sequence[Vec3]] | None,
) -> MapLandmark:
    motion = classify_motion(track)
    last = track.observations[-1]
    anchor = _nearest(last.t_ns, checkpoints)
    if origin is None or anchor is None:
        lat: float | None = None
        lon: float | None = None
        alt: float | None = None
        offset_ns: int | None = None
        anchor_t_ns: int | None = None
    else:
        lat, lon, alt = _enu_to_wgs84(last.centroid, origin)
        offset_ns = last.t_ns - anchor.t_ns
        anchor_t_ns = anchor.t_ns
    cloud: tuple[Vec3, ...] | None = None
    if mask_points is not None and track.track_id in mask_points:
        cloud = tuple(mask_points[track.track_id])
    return MapLandmark(
        id=str(track.track_id),
        xyz=last.centroid,
        lat=lat,
        lon=lon,
        alt=alt,
        label=track.label,
        description=descriptions.get(track.track_id, ""),
        model_id=model_ids.get(track.track_id, ""),
        motion=motion,
        offset_ns=offset_ns,
        anchor_t_ns=anchor_t_ns,
        t_ns=last.t_ns,
        observations=tuple(
            MapObservation(observation.t_ns, observation.centroid)
            for observation in track.observations
        ),
        mask_points=cloud,
    )


def _xyz_json(point: Vec3) -> dict[str, float]:
    return {"x": point.x, "y": point.y, "z": point.z}


def _landmark_json(landmark: MapLandmark) -> dict[str, object]:
    mask: object
    if landmark.mask_points is None:
        mask = None
    else:
        mask = [_xyz_json(point) for point in landmark.mask_points]
    return {
        "id": landmark.id,
        "xyz": _xyz_json(landmark.xyz),
        "lat": landmark.lat,
        "lon": landmark.lon,
        "alt": landmark.alt,
        "label": landmark.label,
        "description": landmark.description,
        "model_id": landmark.model_id,
        "motion": landmark.motion.value,
        "t_ns": landmark.t_ns,
        "anchor_t_ns": landmark.anchor_t_ns,
        "offset_ns": landmark.offset_ns,
        "observations": [
            {"t_ns": observation.t_ns, "xyz": _xyz_json(observation.xyz)}
            for observation in landmark.observations
        ],
        "mask_points": mask,
    }


def _snapshot_json(snapshot: SemanticMapSnapshot) -> dict[str, object]:
    origin: object
    if snapshot.origin is None:
        origin = None
    else:
        origin = {
            "t_ns": snapshot.origin.t_ns,
            "lat": snapshot.origin.lat,
            "lon": snapshot.origin.lon,
            "alt": snapshot.origin.alt,
            "accuracy_m": snapshot.origin.accuracy_m,
        }
    return {
        "schema": snapshot.schema,
        "origin": origin,
        "landmarks": [_landmark_json(landmark) for landmark in snapshot.landmarks],
        "dynamic": [_landmark_json(landmark) for landmark in snapshot.dynamic],
        "meta_calls": [_meta_call_json(call) for call in snapshot.meta_calls],
    }


def _meta_call_json(call: MetaCallRecord) -> dict[str, object]:
    return {
        "role": call.role,
        "model_id": call.model_id,
        "elapsed_s": call.elapsed_s,
        "confidences": list(call.confidences),
    }


def _parse_snapshot(raw: object) -> SemanticMapSnapshot:
    document = _as_object(raw, "snapshot")
    schema = _as_str(document.get("schema"), "schema")
    if schema != SNAPSHOT_SCHEMA:
        raise ValueError(f"unsupported snapshot schema {schema!r}")
    return SemanticMapSnapshot(
        schema=schema,
        origin=_parse_origin(document.get("origin")),
        landmarks=_parse_landmarks(document.get("landmarks"), "landmarks"),
        dynamic=_parse_landmarks(document.get("dynamic"), "dynamic"),
        meta_calls=_parse_meta_calls(document.get("meta_calls", ())),
    )


def _parse_meta_calls(raw: object) -> tuple[MetaCallRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("meta_calls must be a list")
    records: list[MetaCallRecord] = []
    for index, item in enumerate(raw):
        body = _as_object(item, f"meta_calls[{index}]")
        confidences_raw = body.get("confidences", [])
        if not isinstance(confidences_raw, list):
            raise ValueError(f"meta_calls[{index}].confidences must be a list")
        confidences: list[float | None] = []
        for confidence in confidences_raw:
            if confidence is None:
                confidences.append(None)
            else:
                confidences.append(_as_float(confidence, f"meta_calls[{index}].confidences"))
        records.append(
            MetaCallRecord(
                role=_as_str(body.get("role"), f"meta_calls[{index}].role"),
                model_id=_as_str(body.get("model_id"), f"meta_calls[{index}].model_id"),
                elapsed_s=_as_float(body.get("elapsed_s"), f"meta_calls[{index}].elapsed_s"),
                confidences=tuple(confidences),
            )
        )
    return tuple(records)


def _parse_origin(raw: object) -> MapOrigin | None:
    if raw is None:
        return None
    body = _as_object(raw, "origin")
    return MapOrigin(
        t_ns=_as_int(body.get("t_ns"), "origin.t_ns"),
        lat=_as_float(body.get("lat"), "origin.lat"),
        lon=_as_float(body.get("lon"), "origin.lon"),
        alt=_as_float(body.get("alt"), "origin.alt"),
        accuracy_m=_as_float(body.get("accuracy_m"), "origin.accuracy_m"),
    )


def _parse_landmarks(raw: object, label: str) -> tuple[MapLandmark, ...]:
    return tuple(_parse_landmark(_as_object(item, label)) for item in _as_list(raw, label))


def _parse_landmark(body: dict[str, object]) -> MapLandmark:
    return MapLandmark(
        id=_as_str(body.get("id"), "id"),
        xyz=_as_xyz(body.get("xyz"), "xyz"),
        lat=_as_optional_float(body.get("lat"), "lat"),
        lon=_as_optional_float(body.get("lon"), "lon"),
        alt=_as_optional_float(body.get("alt"), "alt"),
        label=_as_str(body.get("label"), "label"),
        description=_as_str(body.get("description"), "description"),
        model_id=_as_str(body.get("model_id"), "model_id"),
        motion=_as_motion(body.get("motion")),
        offset_ns=_as_optional_int(body.get("offset_ns"), "offset_ns"),
        anchor_t_ns=_as_optional_int(body.get("anchor_t_ns"), "anchor_t_ns"),
        t_ns=_as_int(body.get("t_ns"), "t_ns"),
        observations=_parse_observations(body.get("observations")),
        mask_points=_parse_mask(body.get("mask_points")),
    )


def _parse_observations(raw: object) -> tuple[MapObservation, ...]:
    observations: list[MapObservation] = []
    for item in _as_list(raw, "observations"):
        body = _as_object(item, "observation")
        observations.append(
            MapObservation(
                t_ns=_as_int(body.get("t_ns"), "observation.t_ns"),
                xyz=_as_xyz(body.get("xyz"), "observation.xyz"),
            )
        )
    return tuple(observations)


def _parse_mask(raw: object) -> tuple[Vec3, ...] | None:
    if raw is None:
        return None
    return tuple(_as_xyz(item, "mask_points") for item in _as_list(raw, "mask_points"))


def _as_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    pairs: list[tuple[str, object]] = []
    for key in value:
        if not isinstance(key, str):
            raise ValueError(f"{label} has a non-string key")
        item: object = value[key]
        pairs.append((key, item))
    return dict(pairs)


def _as_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    items: list[object] = []
    for item in value:
        boxed: object = item
        items.append(boxed)
    return items


def _as_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _as_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _as_optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _as_int(value, label)


def _as_float(value: object, label: str) -> float:
    # bool is an int, and it is not a JSON number we accept.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be a number")
    return float(value)


def _as_optional_float(value: object, label: str) -> float | None:
    if value is None:
        return None
    return _as_float(value, label)


def _as_xyz(value: object, label: str) -> Vec3:
    body = _as_object(value, label)
    return Vec3(
        _as_float(body.get("x"), f"{label}.x"),
        _as_float(body.get("y"), f"{label}.y"),
        _as_float(body.get("z"), f"{label}.z"),
    )


def _as_motion(value: object) -> Motion:
    if not isinstance(value, str):
        raise ValueError("motion must be a string")
    try:
        return Motion(value)
    except ValueError as exc:
        raise ValueError(f"unsupported motion {value!r}") from exc
