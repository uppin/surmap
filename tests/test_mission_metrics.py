"""Impact metrics compare detections with the disaster-block ground truth."""

import math
from pathlib import Path

import pytest

from surmap.mission.metrics import SurvivorDetection, score_survivors
from surmap.simulation.disaster_world import (
    DisasterGroundTruth,
    MapEnu,
    PersonGroundTruth,
    load_disaster_ground_truth,
)
from surmap.types import Vec3

_START_NS = 1_000_000_000
_SEEN_NS = 4_000_000_000


def _person(person_id: str, east_m: float, north_m: float, up_m: float = 0.0) -> PersonGroundTruth:
    return PersonGroundTruth(
        person_id,
        "standing",
        MapEnu(east_m, north_m, up_m),
        0.0,
        0.0,
        0.0,
        488.0,
    )


def _truth(*people: PersonGroundTruth) -> DisasterGroundTruth:
    return DisasterGroundTruth(
        "test_block",
        people,
        (),
        47.0,
        8.0,
        488.0,
        0.0,
        "ENU",
        "EARTH_WGS84",
    )


def _detection(
    east_m: float, north_m: float, up_m: float = 0.0, label: str = "survivor"
) -> SurvivorDetection:
    return SurvivorDetection(Vec3(east_m, north_m, up_m), _SEEN_NS, label)


def test_one_nearby_detection_counts_as_found_and_the_other_person_stays_missed() -> None:
    # Given two people and one detection one metre east of the first
    truth = _truth(_person("south", 0.0, 10.0), _person("north", 0.0, 40.0))

    # When the detections are scored inside a 3 m radius
    metrics = score_survivors(
        truth,
        (_detection(1.0, 10.0),),
        mission_start_ns=_START_NS,
        match_radius_m=3.0,
        basis="fixtures",
    )

    # Then only the nearby person is found, and the error and time are computed
    assert metrics.found == 1
    assert metrics.total == 2
    assert metrics.matched_ids == ("south",)
    assert metrics.missed_ids == ("north",)
    assert metrics.mean_position_error_m == 1.0
    assert metrics.time_to_first_detection_s == 3.0
    assert metrics.basis == "fixtures"


def test_a_detection_outside_the_match_radius_is_not_a_find() -> None:
    # Given one person and a detection four metres away
    truth = _truth(_person("south", 0.0, 10.0))

    # When the match radius is 3 m
    metrics = score_survivors(
        truth,
        (_detection(0.0, 14.0),),
        mission_start_ns=_START_NS,
        match_radius_m=3.0,
        basis="fixtures",
    )

    # Then nobody is found and the means stay empty
    assert metrics.found == 0
    assert metrics.total == 1
    assert metrics.mean_position_error_m is None
    assert metrics.time_to_first_detection_s is None
    assert metrics.missed_ids == ("south",)


def test_two_detections_of_one_person_count_once_using_the_closer_point() -> None:
    # Given one person and two survivor detections, one closer than the other
    truth = _truth(_person("plaza", 5.0, 5.0))

    # When both fall inside the radius
    metrics = score_survivors(
        truth,
        (_detection(5.0, 7.0), _detection(6.0, 5.0)),
        mission_start_ns=_START_NS,
        match_radius_m=3.0,
        basis="fixtures",
    )

    # Then the person is found once, at the closer one-metre error
    assert metrics.found == 1
    assert metrics.total == 1
    assert metrics.mean_position_error_m == 1.0


def test_a_car_label_is_not_scored_as_a_survivor() -> None:
    # Given a detection sitting on a person but labelled as a vehicle
    truth = _truth(_person("south", 1.0, 2.0))

    # When it is scored
    metrics = score_survivors(
        truth,
        (_detection(1.0, 2.0, label="car"),),
        mission_start_ns=_START_NS,
        match_radius_m=3.0,
        basis="fixtures",
    )

    # Then it does not count
    assert metrics.found == 0
    assert metrics.total == 1


def test_the_total_is_the_people_array_in_the_ground_truth_file() -> None:
    # Given the disaster-block scoring file, not a fixed head count
    truth = load_disaster_ground_truth()
    payload_people = _people_array()

    # When every person is detected exactly on their map point
    detections = tuple(
        SurvivorDetection(
            Vec3(person.map_enu.x_m, person.map_enu.y_m, person.map_enu.z_m),
            _SEEN_NS,
            "survivor",
        )
        for person in truth.people
    )
    metrics = score_survivors(
        truth,
        detections,
        mission_start_ns=_START_NS,
        match_radius_m=3.0,
        basis="fixtures",
    )

    # Then the total is that file's people array
    assert metrics.total == len(truth.people)
    assert metrics.total == len(payload_people)
    assert metrics.found == metrics.total
    assert metrics.mean_position_error_m == 0.0
    assert metrics.basis == "fixtures"


def _people_array() -> list[object]:
    import json

    path = Path(__file__).resolve().parents[1] / (
        "docs/simulation/gz/worlds/disaster_block_ground_truth.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    people = payload["people"]
    assert isinstance(people, list)
    return people


def test_mean_error_is_the_euclidean_distance_of_the_matched_pair() -> None:
    # Given a detection offset by 0.6 m east and 0.8 m north
    truth = _truth(_person("edge", 2.0, 3.0, 1.0))

    metrics = score_survivors(
        truth,
        (_detection(2.6, 3.8, 1.0),),
        mission_start_ns=_START_NS,
        match_radius_m=3.0,
        basis="live",
    )

    # Then the mean error is the hypotenuse, and the basis is the caller's
    assert metrics.mean_position_error_m == pytest.approx(math.sqrt(0.6**2 + 0.8**2))
    assert metrics.basis == "live"
