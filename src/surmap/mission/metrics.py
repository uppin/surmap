"""Score detected survivors against the disaster-block ground truth.

The total is ``len(truth.people)``. Nothing in this module assumes a
fixed head count. Offline runs set ``basis`` to ``fixtures`` so a
reader can see the figures were computed from the recorded fixture,
not from a live flight.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from surmap.simulation.disaster_world import DisasterGroundTruth
from surmap.types import Vec3

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "offline_perception.json"


@dataclass(frozen=True)
class SurvivorDetection:
    """One labelled point in map ENU metres."""

    xyz: Vec3
    t_ns: int
    label: str


@dataclass(frozen=True)
class OfflinePerception:
    """Recorded offsets that turn each ground-truth person into a fixture detection."""

    east_offset_m: float
    north_offset_m: float
    up_offset_m: float
    mission_start_ns: int
    first_detection_ns: int
    step_ns: int
    skip_ids: tuple[str, ...]
    match_radius_m: float

    @property
    def expected_error_m(self) -> float:
        return math.sqrt(self.east_offset_m**2 + self.north_offset_m**2 + self.up_offset_m**2)

    @property
    def time_to_first_s(self) -> float:
        return (self.first_detection_ns - self.mission_start_ns) / 1_000_000_000


@dataclass(frozen=True)
class ImpactMetrics:
    """Found-of-total, mean position error, and time to the first match."""

    found: int
    total: int
    mean_position_error_m: float | None
    time_to_first_detection_s: float | None
    basis: str
    matched_ids: tuple[str, ...]
    missed_ids: tuple[str, ...]
    match_radius_m: float


def load_offline_perception(path: Path | None = None) -> OfflinePerception:
    """Load the recorded offset fixture. It does not contain a survivor count."""
    fixture = path if path is not None else _FIXTURE
    payload: object = json.loads(fixture.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("offline perception fixture must be an object")
    raw = {str(key): value for key, value in payload.items()}
    skip = raw.get("skip_ids", [])
    if not isinstance(skip, list) or not all(isinstance(item, str) for item in skip):
        raise ValueError("skip_ids must be a list of strings")
    return OfflinePerception(
        east_offset_m=_float(raw, "east_offset_m"),
        north_offset_m=_float(raw, "north_offset_m"),
        up_offset_m=_float(raw, "up_offset_m"),
        mission_start_ns=_int(raw, "mission_start_ns"),
        first_detection_ns=_int(raw, "first_detection_ns"),
        step_ns=_int(raw, "step_ns"),
        skip_ids=tuple(skip),
        match_radius_m=_float(raw, "match_radius_m"),
    )


def score_survivors(
    truth: DisasterGroundTruth,
    detections: tuple[SurvivorDetection, ...] | list[SurvivorDetection],
    *,
    mission_start_ns: int,
    match_radius_m: float,
    basis: str,
) -> ImpactMetrics:
    """Greedy nearest match of survivor-labelled points to ground-truth people."""
    if match_radius_m < 0:
        raise ValueError("match_radius_m must be non-negative")
    candidates = [item for item in detections if _is_survivor(item.label)]
    pairs: list[tuple[float, int, int]] = []
    for detection_index, detection in enumerate(candidates):
        for person_index, person in enumerate(truth.people):
            distance_m = _distance(
                detection.xyz,
                person.map_enu.x_m,
                person.map_enu.y_m,
                person.map_enu.z_m,
            )
            if distance_m <= match_radius_m:
                pairs.append((distance_m, detection_index, person_index))
    pairs.sort(key=lambda item: (item[0], item[2], item[1]))
    used_detections: set[int] = set()
    used_people: set[int] = set()
    matched: list[tuple[int, int, float]] = []
    for distance_m, detection_index, person_index in pairs:
        if detection_index in used_detections or person_index in used_people:
            continue
        used_detections.add(detection_index)
        used_people.add(person_index)
        matched.append((person_index, detection_index, distance_m))
    matched.sort(key=lambda item: item[0])
    matched_ids = tuple(truth.people[person_index].id for person_index, _, _ in matched)
    missed_ids = tuple(
        person.id for index, person in enumerate(truth.people) if index not in used_people
    )
    if matched:
        mean_error = sum(distance_m for _, _, distance_m in matched) / len(matched)
        first_ns = min(candidates[detection_index].t_ns for _, detection_index, _ in matched)
        time_s: float | None = (first_ns - mission_start_ns) / 1_000_000_000
    else:
        mean_error = None
        time_s = None
    return ImpactMetrics(
        found=len(matched),
        total=len(truth.people),
        mean_position_error_m=mean_error,
        time_to_first_detection_s=time_s,
        basis=basis,
        matched_ids=matched_ids,
        missed_ids=missed_ids,
        match_radius_m=match_radius_m,
    )


def _is_survivor(label: str) -> bool:
    text = label.lower()
    return "survivor" in text or "person" in text


def _distance(point: Vec3, east_m: float, north_m: float, up_m: float) -> float:
    return math.sqrt((point.x - east_m) ** 2 + (point.y - north_m) ** 2 + (point.z - up_m) ** 2)


def _float(raw: dict[str, object], key: str) -> float:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be a number")
    return float(value)


def _int(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value
