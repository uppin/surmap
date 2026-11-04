"""Drone nests in the station: where a pad may stand, how many drones it houses, what they are
called, and the `earthquake-fleet` preset. The renderer applies the same rules
(examples/bevy-sitl-poc/src/scene_manifest/tests/fleet.rs)."""

from __future__ import annotations

import functools
import json
from pathlib import Path

import pytest

from surmap.simulation.fleet_nests import Nest, nests_of
from surmap.simulation.manifest_checks import object_list
from surmap.simulation.scenario_manifest import (
    Manifest,
    ScenarioInvalid,
    add_element,
    load_presets,
    validate_manifest,
)
from tests.sim_fakes import POC_ASSETS, element_ids

GOLDEN = Path(__file__).parent / "fixtures" / "sim_scenario" / "fleet-nests.json"

# East 34..46, north -6..6, its roof 15 m up.
TOWER: dict[str, object] = {
    "kind": "building",
    "id": "tower-1",
    "material": "facade",
    "size_m": [12.0, 12.0, 15.0],
    "position_enu": [40.0, 0.0, 0.0],
}
# East -45..-35, north -50..50, its top 0.6 m up.
FLOODWATER: dict[str, object] = {
    "kind": "box",
    "id": "floodwater",
    "material": "water",
    "size_m": [10.0, 100.0, 0.6],
    "position_enu": [-40.0, 0.0, 0.0],
    "water": True,
}


def a_nest(
    nest_id: str = "nest-a", at: tuple[float, float, float] = (0.0, 20.0, 0.0), **fields: object
) -> dict[str, object]:
    return {"kind": "drone_nest", "id": nest_id, "position_enu": list(at), **fields}


def a_box(box_id: str) -> dict[str, object]:
    return {
        "kind": "box",
        "id": box_id,
        "material": "ground",
        "size_m": [1.0, 1.0, 1.0],
        "position_enu": [0.0, -30.0, 0.0],
    }


def a_row_of_nests(count: int) -> list[dict[str, object]]:
    """`count` one-drone nests 10 m apart along north 60, from east -40."""
    return [a_nest(f"nest-{i}", (i * 10.0 - 40.0, 60.0, 0.0)) for i in range(count)]


def a_lot() -> Manifest:
    """The empty lot (collider ground, its top at 0) with `tower-1` and `floodwater`."""
    lot = load_presets(POC_ASSETS)["empty-lot"]
    return add_element(add_element(lot, TOWER), FLOODWATER)


def a_lot_with(*elements: dict[str, object]) -> Manifest:
    return functools.reduce(add_element, elements, a_lot())


def drone_ids_of(nests: tuple[Nest, ...]) -> list[str]:
    return [drone for nest in nests for drone in nest.drone_ids]


def the_nest(manifest: Manifest, nest_id: str) -> Nest:
    (found,) = [nest for nest in nests_of(manifest) if nest.id == nest_id]
    return found


def _up(triple: object) -> float:
    assert isinstance(triple, list)
    return float(triple[2])


def building_tops(manifest: Manifest) -> list[float]:
    """The roof height of every building in the scene, m."""
    buildings = [e for e in object_list(manifest, "elements") if e.get("kind") == "building"]
    return [_up(b["position_enu"]) + _up(b["size_m"]) for b in buildings]


def test_a_nest_on_open_ground_is_kept_with_one_drone_facing_east() -> None:
    # Given the lot
    # When a nest with no heading or drone count is placed on its open ground
    scenario = a_lot_with(a_nest("nest-a", (0.0, 20.0, 0.0)))

    # Then the nest houses one drone, named after it, and faces east
    assert nests_of(scenario) == (Nest("nest-a", (0.0, 20.0, 0.0), 0.0, ("nest-a-d1",)),)


def test_a_nest_names_its_drones_after_itself_in_order() -> None:
    # When a nest housing three drones is placed
    scenario = a_lot_with(a_nest("nest-a", drones=3))

    # Then its drones are nest-a-d1 to nest-a-d3
    assert drone_ids_of(nests_of(scenario)) == ["nest-a-d1", "nest-a-d2", "nest-a-d3"]


def test_a_nest_inside_a_building_is_refused_with_the_rule() -> None:
    # Then a pad on the ground inside the tower is refused, naming the tower
    with pytest.raises(ScenarioInvalid, match="nest-a.*tower-1"):
        a_lot_with(a_nest("nest-a", (40.0, 0.0, 0.0)))


def test_a_nest_on_a_roof_is_accepted() -> None:
    # When a nest is placed on the tower's roof, 15 m up
    scenario = a_lot_with(a_nest("nest-roof", (40.0, 0.0, 15.0)))

    # Then the scenario keeps it
    assert [nest.id for nest in nests_of(scenario)] == ["nest-roof"]


def test_a_square_pad_beside_a_building_is_accepted() -> None:
    # When an unturned pad is placed with its east edge 0.3 m short of the tower's west wall
    scenario = a_lot_with(a_nest("nest-a", (32.5, 0.0, 0.0)))

    # Then the scenario keeps it
    assert [nest.id for nest in nests_of(scenario)] == ["nest-a"]


def test_a_pad_turned_so_its_corner_reaches_a_building_is_refused() -> None:
    # Then the same pad turned 45°, its corner 0.2 m into the tower, is refused
    with pytest.raises(ScenarioInvalid, match="nest-a.*tower-1"):
        a_lot_with(a_nest("nest-a", (32.5, 0.0, 0.0), yaw_deg=45.0))


def test_a_nest_on_water_is_refused_with_the_rule() -> None:
    # Then a pad on the floodwater's top is refused, naming the water
    with pytest.raises(ScenarioInvalid, match="nest-a.*water"):
        a_lot_with(a_nest("nest-a", (-40.0, 10.0, 0.6)))


def test_a_nest_outside_the_bounds_is_refused_with_the_rule() -> None:
    # Then a pad 600 m east of the origin is refused, naming the 500 m bound
    with pytest.raises(ScenarioInvalid, match="nest-a.*500"):
        a_lot_with(a_nest("nest-a", (600.0, 0.0, 0.0)))


def test_a_nest_higher_than_sixty_metres_is_refused_with_the_rule() -> None:
    # Then a pad 75 m up is refused, naming the 60 m ceiling
    with pytest.raises(ScenarioInvalid, match="nest-a.*60"):
        a_lot_with(a_nest("nest-a", (0.0, 20.0, 75.0)))


def test_a_nest_too_close_to_another_nest_is_refused_with_the_rule() -> None:
    # Then a second nest 4 m from the first is refused, naming both and the 6 m spacing
    with pytest.raises(ScenarioInvalid, match="nest-b.*nest-a.*6"):
        a_lot_with(a_nest("nest-a", (0.0, 20.0, 0.0)), a_nest("nest-b", (4.0, 20.0, 0.0)))


def test_nests_six_metres_apart_are_accepted() -> None:
    # When two nests are placed exactly 6 m apart
    scenario = a_lot_with(a_nest("nest-a", (0.0, 20.0, 0.0)), a_nest("nest-b", (6.0, 20.0, 0.0)))

    # Then the scenario keeps both
    assert [nest.id for nest in nests_of(scenario)] == ["nest-a", "nest-b"]


def test_a_nest_with_five_drones_is_refused_with_the_rule() -> None:
    # Then a nest housing five drones is refused, naming the four-drone limit
    with pytest.raises(ScenarioInvalid, match="nest-a.*drones.*4"):
        a_lot_with(a_nest("nest-a", drones=5))


def test_a_nest_with_no_drones_is_refused_with_the_rule() -> None:
    # Then a nest housing no drone is refused
    with pytest.raises(ScenarioInvalid, match="nest-a.*drones"):
        a_lot_with(a_nest("nest-a", drones=0))


def test_a_nest_whose_drone_id_is_taken_is_refused_with_the_rule() -> None:
    # Given the lot holding a box called nest-a-d1
    lot = a_lot_with(a_box("nest-a-d1"))

    # Then a nest whose first drone would be nest-a-d1 is refused as a duplicate
    with pytest.raises(ScenarioInvalid, match="duplicate id 'nest-a-d1'"):
        add_element(lot, a_nest("nest-a"))


def test_an_element_may_not_take_the_id_of_a_nests_drone() -> None:
    # Given the lot with a two-drone nest
    lot = a_lot_with(a_nest("nest-a", drones=2))

    # Then a box called after the nest's second drone is refused as a duplicate
    with pytest.raises(ScenarioInvalid, match="duplicate id 'nest-a-d2'"):
        add_element(lot, a_box("nest-a-d2"))


def test_a_nest_id_outside_letters_digits_and_dashes_is_refused() -> None:
    # Then a nest called nest_a is refused, naming the id rule
    with pytest.raises(ScenarioInvalid, match="nest_a.*id"):
        a_lot_with(a_nest("nest_a"))


def test_a_scene_holds_eight_nests_at_most() -> None:
    # Then the ninth nest in a row is refused, naming the limit
    with pytest.raises(ScenarioInvalid, match="at most 8 nests"):
        a_lot_with(*a_row_of_nests(9))


def test_nests_of_lists_only_the_nests_in_manifest_order() -> None:
    # Given a manifest with a box between two nests (read, not validated)
    manifest: Manifest = {
        "elements": [
            a_nest("nest-b", (10.0, 0.0, 0.0), drones=2, yaw_deg=180.0),
            a_box("crate"),
            a_nest("nest-a", (-10.0, 0.0, 0.0)),
        ]
    }

    # When its nests are read
    nests = nests_of(manifest)

    # Then they come in manifest order, each with its heading and drones
    assert nests == (
        Nest("nest-b", (10.0, 0.0, 0.0), 180.0, ("nest-b-d1", "nest-b-d2")),
        Nest("nest-a", (-10.0, 0.0, 0.0), 0.0, ("nest-a-d1",)),
    )


def test_the_earthquake_fleet_preset_has_three_nests_and_five_drones() -> None:
    # When the presets are loaded
    fleet = load_presets(POC_ASSETS)["earthquake-fleet"]

    # Then the fleet has two two-drone nests on the ground and one single-drone nest on a roof
    assert [(nest.id, len(nest.drone_ids)) for nest in nests_of(fleet)] == [
        ("nest-sw", 2),
        ("nest-ne", 2),
        ("nest-roof", 1),
    ]


def test_the_earthquake_fleet_roof_nest_stands_on_a_buildings_top() -> None:
    # Given the earthquake-fleet preset
    fleet = load_presets(POC_ASSETS)["earthquake-fleet"]

    # When its roof nest is found
    roof = the_nest(fleet, "nest-roof")

    # Then its deck is the top of one of the block's buildings
    assert roof.pad_enu[2] in building_tops(fleet)


def test_the_earthquake_fleet_preset_is_the_block_with_its_nests_added() -> None:
    # Given the presets
    presets = load_presets(POC_ASSETS)

    # When the fleet's element ids are listed
    ids = element_ids(presets["earthquake-fleet"])

    # Then they are the block's, then the three nests
    assert ids == [*element_ids(presets["earthquake-block"]), "nest-sw", "nest-ne", "nest-roof"]


def test_the_fleet_golden_the_renderer_parses_is_a_valid_scenario() -> None:
    # Given the shared golden
    golden: Manifest = json.loads(GOLDEN.read_text(encoding="utf-8"))

    # When the station validates it
    validate_manifest(golden)

    # Then its nests house the five drones the renderer names too
    assert drone_ids_of(nests_of(golden)) == [
        "nest-sw-d1",
        "nest-sw-d2",
        "nest-ne-d1",
        "nest-ne-d2",
        "nest-roof-d1",
    ]
