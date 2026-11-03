"""Building presets (Overture vocabulary), districts and building fires in scenario manifests."""

from collections.abc import Callable

import pytest

from surmap.simulation.scenario_manifest import (
    OVERTURE_FACADES,
    OVERTURE_ROOFS,
    ScenarioInvalid,
    add_building_fire,
    add_element,
    building_presets,
    load_presets,
    remove_building_fire,
    remove_district,
    set_district,
    style_building,
    validate_manifest,
)
from tests.sim_fakes import POC_ASSETS, building, building_fire_ids, district_ids, element_ids


def a_lot_with_a_tower() -> dict[str, object]:
    lot = load_presets(POC_ASSETS)["empty-lot"]
    with_core = set_district(
        lot, "core", "downtown", position_enu=(0.0, 0.0, 0.0), size_m=(120.0, 80.0), seed=4
    )
    tower = {
        "kind": "building",
        "id": "tower-2",
        "size_m": [18.0, 18.0, 42.0],
        "position_enu": [30.0, 10.0, 0.0],
    }
    return add_element(with_core, tower)


def test_every_overture_facade_and_roof_value_is_a_listed_preset() -> None:
    presets = building_presets(POC_ASSETS)

    assert set(OVERTURE_FACADES) <= set(presets.facades)
    assert set(OVERTURE_ROOFS) <= set(presets.roofs)
    assert {"old-town", "downtown", "industrial", "suburban"} <= set(presets.districts)


def test_a_building_inside_a_district_needs_no_material_of_its_own() -> None:
    scenario = a_lot_with_a_tower()

    validate_manifest(scenario)
    assert district_ids(scenario) == ["core"]
    assert "material" not in building(scenario, "tower-2")


def test_a_building_is_styled_over_its_district_without_touching_the_original() -> None:
    # Given a tower in a downtown district
    scenario = a_lot_with_a_tower()

    # When the agent makes it a glass tower with a metal roof and 12 floors
    styled = style_building(
        scenario, "tower-2", facade="glass", roof="metal", roof_shape="flat", floors=12
    )

    # Then the tower carries those, and the original does not
    assert {
        k: building(styled, "tower-2").get(k) for k in ("facade", "roof", "roof_shape", "floors")
    } == {
        "facade": "glass",
        "roof": "metal",
        "roof_shape": "flat",
        "floors": 12,
    }
    assert "facade" not in building(scenario, "tower-2")


def test_glazing_and_colours_are_styled_too() -> None:
    styled = style_building(
        a_lot_with_a_tower(),
        "tower-2",
        facade="plaster",
        facade_colour=(0.8, 0.7, 0.5),
        glazing={"kind": "punched", "window_ratio": 0.3},
    )

    assert building(styled, "tower-2")["facade_colour"] == [0.8, 0.7, 0.5]
    assert building(styled, "tower-2")["glazing"] == {"kind": "punched", "window_ratio": 0.3}


def test_a_preset_file_path_is_accepted_as_a_facade() -> None:
    styled = style_building(
        a_lot_with_a_tower(), "tower-2", facade="building/facades/brick.facade.json"
    )

    validate_manifest(styled)


Manifest = dict[str, object]

REFUSED_STYLES: list[tuple[Callable[[Manifest], Manifest], str]] = [
    (lambda m: style_building(m, "tower-2", facade="marble"), "marble"),
    (lambda m: style_building(m, "tower-2", roof="building/facades/brick.facade.json"), "roof"),
    (lambda m: style_building(m, "tower-2", roof_shape="dome"), "dome"),
    (lambda m: style_building(m, "tower-2", floors=0), "floors"),
    (lambda m: style_building(m, "tower-2", glazing={"kind": "stained"}), "stained"),
    (lambda m: style_building(m, "tower-2", facade_colour=(1.5, 0.0, 0.0)), "facade_colour"),
]


@pytest.mark.parametrize(("edit", "reason"), REFUSED_STYLES)
def test_a_style_that_cannot_render_is_refused(
    edit: Callable[[Manifest], Manifest], reason: str
) -> None:
    with pytest.raises(ScenarioInvalid, match=reason):
        edit(a_lot_with_a_tower())


def test_styling_something_that_is_not_a_building_is_refused() -> None:
    with pytest.raises(ScenarioInvalid, match="ground"):
        style_building(a_lot_with_a_tower(), "ground", facade="brick")


def test_a_district_with_an_unknown_preset_is_refused() -> None:
    lot = load_presets(POC_ASSETS)["empty-lot"]

    with pytest.raises(ScenarioInvalid, match="favela"):
        set_district(lot, "core", "favela", position_enu=(0.0, 0.0, 0.0), size_m=(10.0, 10.0))


def test_a_building_left_outside_every_district_without_a_material_is_refused() -> None:
    with pytest.raises(ScenarioInvalid, match="tower-2"):
        remove_district(a_lot_with_a_tower(), "core")


def test_a_building_fire_is_lit_and_put_out() -> None:
    scenario = style_building(a_lot_with_a_tower(), "tower-2", floors=12)

    lit = add_building_fire(scenario, "blaze-1", building="tower-2", floor=3, start_s=5.0)
    out = remove_building_fire(lit, "blaze-1")

    assert building_fire_ids(lit) == ["blaze-1"]
    assert building_fire_ids(out) == []


@pytest.mark.parametrize(
    ("fire_id", "target", "floor", "reason"),
    [
        ("blaze-1", "tower-9", 3, "tower-9"),
        ("blaze-1", "tower-2", 12, "floor"),
        ("blaze-1", "ground", 0, "ground"),
        ("tower-2", "tower-2", 0, "tower-2"),
    ],
)
def test_a_building_fire_that_cannot_burn_is_refused(
    fire_id: str, target: str, floor: int, reason: str
) -> None:
    scenario = style_building(a_lot_with_a_tower(), "tower-2", floors=12)

    with pytest.raises(ScenarioInvalid, match=reason):
        add_building_fire(scenario, fire_id, building=target, floor=floor)


def test_the_showcase_preset_puts_every_shipped_district_side_by_side() -> None:
    showcase = load_presets(POC_ASSETS)["district-showcase"]

    assert sorted(str(d["preset"]) for d in showcase_districts(showcase)) == [
        "downtown",
        "industrial",
        "old-town",
        "suburban",
    ]
    assert len(element_ids(showcase)) == 1 + 4 * 6
    validate_manifest(showcase)


def test_the_downtown_blaze_preset_has_a_glass_tower_burning_on_its_third_floor() -> None:
    blaze = load_presets(POC_ASSETS)["downtown-blaze"]

    (fire,) = showcase_fires(blaze)
    assert (fire["floor"], fire["start_s"]) == (3, 5.0)
    assert building(blaze, str(fire["building"]))["facade"] == "glass"
    validate_manifest(blaze)


def showcase_districts(manifest: dict[str, object]) -> list[dict[str, object]]:
    districts = manifest["districts"]
    assert isinstance(districts, list)
    return [d for d in districts if isinstance(d, dict)]


def showcase_fires(manifest: dict[str, object]) -> list[dict[str, object]]:
    fires = manifest["building_fires"]
    assert isinstance(fires, list)
    return [f for f in fires if isinstance(f, dict)]
