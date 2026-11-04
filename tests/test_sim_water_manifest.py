"""Boats and ships in the station: water surfaces, the rules that keep vessels on them, the
preset."""

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

GOLDEN = Path(__file__).parent / "fixtures" / "sim_scenario" / "flood-rescue.json"

FLOODWATER: dict[str, object] = {
    "kind": "box",
    "id": "floodwater",
    "material": "water",
    "size_m": [10.0, 100.0, 0.6],
    "position_enu": [0.0, 50.0, 0.0],
    "water": True,
}


def a_flooded_street_with(vehicle: dict[str, object]) -> dict[str, object]:
    street = add_element(load_presets(POC_ASSETS)["flood-street"], FLOODWATER)
    return add_element(street, {"kind": "vehicle", "id": "b1", **vehicle})


def test_a_boat_shuttling_along_the_floodwater_is_valid() -> None:
    shuttle = {"node": "follow_path", "enu": [[0.0, 90.0], [0.0, 10.0]], "speed_m_s": 4.0}

    validate_manifest(
        a_flooded_street_with(
            {"class": "boat", "position_enu": [0.0, 10.0, 0.0], "behaviour": shuttle}
        )
    )


@pytest.mark.parametrize(
    ("vehicle", "reason"),
    [
        ({"class": "boat", "position_enu": [40.0, 50.0, 0.0]}, "water"),
        (
            {
                "class": "boat",
                "position_enu": [0.0, 10.0, 0.0],
                "behaviour": {"node": "move_to", "enu": [30.0, 60.0], "speed_m_s": 4.0},
            },
            "30",
        ),
        (
            {
                "class": "ship",
                "position_enu": [0.0, 10.0, 0.0],
                "behaviour": {"node": "wander", "radius_m": 5.0, "speed_m_s": 2.0, "seed": 1},
            },
            "wander",
        ),
        ({"class": "car", "position_enu": [0.0, 10.0, 0.0]}, "water"),
    ],
)
def test_a_vessel_off_its_water_is_refused_with_its_reason(
    vehicle: dict[str, object], reason: str
) -> None:
    with pytest.raises(ScenarioInvalid, match=f"b1.*{reason}|{reason}.*b1"):
        validate_manifest(a_flooded_street_with(vehicle))


def test_a_water_flag_that_is_not_a_boolean_is_refused() -> None:
    street = load_presets(POC_ASSETS)["flood-street"]

    with pytest.raises(ScenarioInvalid, match="floodwater.*water"):
        validate_manifest(add_element(street, {**FLOODWATER, "water": "yes"}))


def test_the_flood_rescue_preset_puts_two_boats_on_floodwater_over_the_flood_street() -> None:
    presets = load_presets(POC_ASSETS)

    rescue = presets["flood-rescue"]

    boats = [v for v in vehicles_of(rescue) if v["class"] == "boat"]
    assert len(boats) == 2 and all(b.get("behaviour") is not None for b in boats)
    assert rescue["weather"] == presets["flood-street"]["weather"]
    validate_manifest(rescue)


def test_the_flood_rescue_preset_is_the_golden_the_renderer_parses() -> None:
    rescue = load_presets(POC_ASSETS)["flood-rescue"]

    assert rescue == json.loads(GOLDEN.read_text(encoding="utf-8"))
