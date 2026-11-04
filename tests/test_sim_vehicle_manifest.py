"""The `vehicle` element in the station: the renderer's rules, the pure edits, the preset."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from surmap.simulation.scenario_manifest import (
    ScenarioInvalid,
    add_element,
    load_presets,
    validate_manifest,
)
from tests.sim_fakes import POC_ASSETS, vehicles_of

GOLDEN = Path(__file__).parent / "fixtures" / "sim_scenario" / "street-traffic.json"


def a_vehicle(**fields: object) -> dict[str, object]:
    return {
        "kind": "vehicle",
        "id": "v1",
        "class": "car",
        "position_enu": [2.5, 0.0, 0.0],
        **fields,
    }


def a_lot_with(vehicle: dict[str, object]) -> dict[str, object]:
    return add_element(load_presets(POC_ASSETS)["empty-lot"], vehicle)


def test_a_bus_with_a_drive_is_a_valid_element() -> None:
    drive = {"node": "follow_path", "enu": [[2.5, 80.0]], "speed_m_s": 8.0}

    validate_manifest(
        a_lot_with(a_vehicle(**{"class": "bus", "yaw_deg": 90.0, "behaviour": drive}))
    )


def test_a_train_takes_carriages() -> None:
    validate_manifest(a_lot_with(a_vehicle(**{"class": "train", "cars": 6})))


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"class": "hovercraft"}, "hovercraft"),
        ({"class": "bus", "cars": 2}, "cars"),
        ({"cars": -1, "class": "train"}, "cars"),
        ({"glb": "models/car.obj"}, "car.obj"),
        ({"glb": "../car.glb"}, "../car.glb"),
        (
            {
                "behaviour": {
                    "node": "set_wind",
                    "from_deg": 0,
                    "speed_m_s": 1,
                    "gust_m_s": 0,
                    "over_s": 1,
                }
            },
            "set_wind",
        ),
        ({"tint": [1.0, 0.5]}, "tint"),
    ],
)
def test_a_vehicle_the_renderer_would_refuse_is_refused_with_its_reason(
    fields: dict[str, object], reason: str
) -> None:
    with pytest.raises(ScenarioInvalid, match=f"v1.*{reason}|{reason}.*v1"):
        validate_manifest(a_lot_with(a_vehicle(**fields)))


def test_the_street_traffic_preset_puts_every_road_and_rail_class_on_the_block() -> None:
    presets = load_presets(POC_ASSETS)

    traffic = presets["street-traffic"]

    vehicles = vehicles_of(traffic)
    assert {v["class"] for v in vehicles} == {"car", "bus", "truck", "train"}
    assert any(v["class"] == "train" and v.get("cars") == 6 for v in vehicles)
    assert any(v.get("behaviour") is None for v in vehicles), "one car is parked"
    validate_manifest(traffic)


def test_the_street_traffic_preset_is_the_golden_the_renderer_parses() -> None:
    traffic = load_presets(POC_ASSETS)["street-traffic"]

    assert traffic == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_the_street_traffic_bus_is_painted_not_the_models_white() -> None:
    traffic = load_presets(POC_ASSETS)["street-traffic"]

    (bus,) = [v for v in vehicles_of(traffic) if v["class"] == "bus"]

    assert bus["tint"] == [1.0, 0.78, 0.1]


def test_the_street_traffic_truck_drives_the_cross_street_side_on_to_the_survey_loop() -> None:
    traffic = load_presets(POC_ASSETS)["street-traffic"]

    (truck,) = [v for v in vehicles_of(traffic) if v["class"] == "truck"]

    # The cross street runs east-west, 10 m wide, centred on north 60 m
    assert (truck["yaw_deg"], truck["position_enu"]) == (0.0, [-45.0, 57.5, 0.0])
