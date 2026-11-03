"""Weather, fires and vegetation in scenario manifests: validation, pure edits and presets."""

import pytest

from surmap.simulation.scenario_manifest import (
    ScenarioInvalid,
    add_element,
    add_fire,
    load_presets,
    remove_fire,
    set_weather,
    validate_manifest,
)
from tests.sim_fakes import (
    POC_ASSETS,
    element_ids,
    fire_ids,
    vegetation_species,
    weather_of,
    wind_of,
)


def the_empty_lot() -> dict[str, object]:
    return load_presets(POC_ASSETS)["empty-lot"]


def a_fire(fire_id: str = "front-1", spread: float = 0.15) -> dict[str, object]:
    return {
        "id": fire_id,
        "ignition_enu": [-20.0, 60.0, 0.0],
        "start_s": 2.0,
        "spread_m_s": spread,
        "max_radius_m": 35.0,
    }


def pines(
    element_id: str = "pines-west", species: str = "species/pine.species.json"
) -> dict[str, object]:
    return {
        "kind": "vegetation",
        "id": element_id,
        "species": species,
        "position_enu": [-40.0, 60.0, 0.0],
        "size_m": [40.0, 60.0],
        "density_per_100m2": 3.0,
        "seed": 11,
    }


def test_setting_the_weather_returns_a_manifest_with_rain_fog_and_wind() -> None:
    # When the empty lot gets a westerly with rain
    edited = set_weather(
        the_empty_lot(),
        rain_mm_h=4.0,
        fog_visibility_m=300.0,
        wind_from_deg=270.0,
        wind_speed_m_s=6.0,
        wind_gust_m_s=2.0,
    )

    # Then the weather is declared, and the original is untouched
    assert edited["weather"] == {
        "rain_mm_h": 4.0,
        "fog_visibility_m": 300.0,
        "wind": {"from_deg": 270.0, "speed_m_s": 6.0, "gust_m_s": 2.0},
    }
    assert "weather" not in the_empty_lot()


def test_a_fire_is_added_and_removed_by_id() -> None:
    # Given the empty lot with a fire
    lit = add_fire(the_empty_lot(), a_fire())

    # When it is removed
    out = remove_fire(lit, "front-1")

    # Then it was there, and now it is not
    assert fire_ids(lit) == ["front-1"]
    assert fire_ids(out) == []


def test_a_fire_reusing_an_element_id_is_refused() -> None:
    # Then a fire called "ground" (the lot's ground box) is refused
    with pytest.raises(ScenarioInvalid, match="ground"):
        add_fire(the_empty_lot(), a_fire("ground"))


def test_a_fire_that_cannot_spread_is_refused() -> None:
    with pytest.raises(ScenarioInvalid, match="spread"):
        add_fire(the_empty_lot(), a_fire(spread=0.0))


def test_a_stand_of_pines_is_an_element() -> None:
    # When pines are planted on the lot
    edited = add_element(the_empty_lot(), pines())

    # Then the stand is listed with the lot's ground
    assert element_ids(edited) == ["ground", "pines-west"]


def test_vegetation_must_name_a_species_file() -> None:
    with pytest.raises(ScenarioInvalid, match="species"):
        add_element(the_empty_lot(), pines(species="models/pine.glb"))


@pytest.mark.parametrize(
    ("weather", "reason"),
    [
        ({"rain_mm_h": -1.0, "wind": {"from_deg": 0.0, "speed_m_s": 1.0}}, "rain"),
        ({"wind": {"from_deg": 0.0, "speed_m_s": -2.0}}, "wind"),
        ({"fog_visibility_m": 0.0, "wind": {"from_deg": 0.0, "speed_m_s": 1.0}}, "fog"),
    ],
)
def test_weather_out_of_range_is_refused(weather: dict[str, object], reason: str) -> None:
    with pytest.raises(ScenarioInvalid, match=reason):
        validate_manifest({**the_empty_lot(), "weather": weather})


def test_the_wildfire_edge_preset_has_pines_grass_wind_and_a_fire_upwind() -> None:
    # Given the wildfire-edge preset
    edge = load_presets(POC_ASSETS)["wildfire-edge"]

    # Then it is valid, has both species, a wind and a fire
    validate_manifest(edge)
    assert vegetation_species(edge) == {
        "species/pine.species.json",
        "species/dry_grass.species.json",
    }
    assert wind_of(edge)["speed_m_s"] == 6.0
    assert len(fire_ids(edge)) == 1


def test_the_flood_street_preset_is_the_block_in_rain_and_fog() -> None:
    # Given the flood-street preset
    flood = load_presets(POC_ASSETS)["flood-street"]

    # Then it is the earthquake block with rain and fog
    validate_manifest(flood)
    assert weather_of(flood)["rain_mm_h"] == 8.0
    assert weather_of(flood)["fog_visibility_m"] == 250.0
    assert "block-ground" in element_ids(flood)
