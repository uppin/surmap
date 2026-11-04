"""Pure scenario-manifest edits and the validation that mirrors the renderer's."""

import json
from pathlib import Path

import pytest

from surmap.simulation.scenario_manifest import (
    ScenarioInvalid,
    add_element,
    load_presets,
    remove_element,
    validate_manifest,
)
from tests.sim_fakes import POC_ASSETS, element_ids


def the_earthquake_block() -> dict[str, object]:
    return load_presets(POC_ASSETS)["earthquake-block"]


def a_building(element_id: str = "tower-1", material: str = "facade") -> dict[str, object]:
    return {
        "kind": "building",
        "id": element_id,
        "material": material,
        "size_m": [12.0, 12.0, 18.0],
        "position_enu": [90.0, 20.0, 0.0],
        "windows": {"material": "glass"},
    }


def test_the_shipped_scene_is_the_earthquake_block_preset_and_valid() -> None:
    # Given the PoC's shipped scene
    shipped = json.loads((POC_ASSETS / "scene.json").read_text(encoding="utf-8"))

    # When the presets are loaded
    presets = load_presets(POC_ASSETS)

    # Then the earthquake block is that scene, and both presets validate
    assert presets["earthquake-block"] == shipped
    for manifest in presets.values():
        validate_manifest(manifest)


def test_the_empty_lot_keeps_the_rig_sky_and_ground_and_nothing_else() -> None:
    # Given the empty-lot preset
    lot = load_presets(POC_ASSETS)["empty-lot"]

    # Then it has the camera, the environment and one ground box, and no models
    assert lot["camera"] == "cameras/elp-stereo-pinhole.camera.json"
    assert element_ids(lot) == ["ground"]
    assert lot["models"] == []


def test_adding_an_element_returns_a_new_manifest_with_it() -> None:
    # Given the earthquake block
    block = the_earthquake_block()

    # When a building is added
    edited = add_element(block, a_building())

    # Then the new manifest has it last and the original is untouched
    assert element_ids(edited)[-1] == "tower-1"
    assert "tower-1" not in element_ids(block)


def test_an_element_reusing_an_id_is_refused() -> None:
    # Given the earthquake block, which has a helipad
    block = the_earthquake_block()

    # Then adding another element called helipad is refused
    with pytest.raises(ScenarioInvalid, match="helipad"):
        add_element(block, a_building("helipad"))


def test_an_element_with_an_undeclared_material_is_refused() -> None:
    # Then a building of marble (no such material) is refused
    with pytest.raises(ScenarioInvalid, match="marble"):
        add_element(the_earthquake_block(), a_building(material="marble"))


def test_removing_an_element_by_id_drops_it() -> None:
    # Given the earthquake block
    block = the_earthquake_block()

    # When its helipad is removed
    edited = remove_element(block, "helipad")

    # Then it is gone, and removing an unknown id is refused
    assert "helipad" not in element_ids(edited)
    with pytest.raises(ScenarioInvalid, match="no-such-thing"):
        remove_element(block, "no-such-thing")


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"version": 2}, "version"),
        ({"camera": "cameras/rig.json"}, "camera"),
        ({"camera": "../rig.camera.json"}, "camera"),
    ],
)
def test_validation_refuses_what_the_renderer_refuses(
    change: dict[str, object], reason: str
) -> None:
    # Given the earthquake block with one field broken
    broken = {**the_earthquake_block(), **change}

    # Then validation names the problem
    with pytest.raises(ScenarioInvalid, match=reason):
        validate_manifest(broken)


def the_map_floor_fixture() -> dict[str, object]:
    path = Path(__file__).parent / "fixtures" / "sim_scenario" / "map-floor.json"
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_shared_map_floor_fixture_validates() -> None:
    # Given the one golden manifest the station and the renderer both read
    # When it is validated
    # Then it passes (the renderer reads the same file in its own tests)
    validate_manifest(the_map_floor_fixture())


def test_a_floor_bigger_than_a_kilometre_is_refused_by_the_station_too() -> None:
    # Given a hand-edited floor two degrees wide on the golden fixture
    manifest = the_map_floor_fixture()
    manifest["map_floor"] = {
        "sw": [54.0, 25.0],
        "ne": [54.001, 27.0],
        "texture": "library/map-floor/abc123.png",
        "zoom": 17,
    }

    # When it is validated
    # Then the station refuses it, exactly as the renderer does
    with pytest.raises(ScenarioInvalid, match="1000"):
        validate_manifest(manifest)


def test_setting_a_map_floor_replaces_the_preset_ground_box() -> None:
    # Given the empty lot, whose only element is the 200 m ground box
    lot = load_presets(POC_ASSETS)["empty-lot"]

    # When a map floor is set
    from surmap.simulation.floor_edits import set_map_floor

    edited = set_map_floor(
        lot, sw=(54.0, 25.0), ne=(54.001, 25.002), texture="library/map-floor/a.png", zoom=17
    )

    # Then the ground box is gone (the floor replaces it) and the manifest validates
    validate_manifest(edited)
    assert element_ids(edited) == []


def test_clearing_a_map_floor_restores_the_ground_box() -> None:
    # Given a floored empty lot
    from surmap.simulation.floor_edits import clear_map_floor, set_map_floor

    lot = load_presets(POC_ASSETS)["empty-lot"]
    floored = set_map_floor(
        lot, sw=(54.0, 25.0), ne=(54.001, 25.002), texture="library/map-floor/a.png", zoom=17
    )

    # When the floor is cleared
    cleared = clear_map_floor(floored)

    # Then there is no floor, the ground box is back, and the manifest validates
    validate_manifest(cleared)
    assert "map_floor" not in cleared
    assert element_ids(cleared) == ["ground"]


def test_setting_a_floor_on_the_block_removes_both_of_its_ground_boxes() -> None:
    # Given the earthquake block, whose ground is an apron and a block-ground box
    from surmap.simulation.floor_edits import set_map_floor

    block = the_earthquake_block()

    # When a floor is set
    edited = set_map_floor(
        block, sw=(54.0, 25.0), ne=(54.001, 25.002), texture="library/map-floor/a.png", zoom=17
    )

    # Then neither ground box remains to hide or flicker against the floor
    assert "apron" not in element_ids(edited)
    assert "block-ground" not in element_ids(edited)
    assert "avenue" in element_ids(edited)


def test_clearing_a_floor_restores_the_presets_own_ground_not_a_default() -> None:
    # Given the floored earthquake block
    from surmap.simulation.floor_edits import clear_map_floor, set_map_floor

    block = the_earthquake_block()
    floored = set_map_floor(
        block, sw=(54.0, 25.0), ne=(54.001, 25.002), texture="library/map-floor/a.png", zoom=17
    )

    # When the floor is cleared
    cleared = clear_map_floor(floored)

    # Then the apron and block-ground are back, with no extra 200 m ground box
    assert "apron" in element_ids(cleared)
    assert "block-ground" in element_ids(cleared)
    assert "ground" not in element_ids(cleared)
