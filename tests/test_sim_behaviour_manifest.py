"""Behaviour trees in scenario manifests: validation per target, pure edits and the preset."""

import pytest

from surmap.simulation.scenario_manifest import (
    ScenarioInvalid,
    add_element,
    behaviour_of,
    load_presets,
    set_behaviour,
    set_weather,
    update_behaviour_node,
    validate_manifest,
)
from tests.sim_fakes import POC_ASSETS, fire_ids, person_ids, wind_of

SMELL_SMOKE: dict[str, object] = {"node": "near_fire", "id": "smell-smoke", "within_m": 20.0}
RUN: dict[str, object] = {
    "node": "flee_from_fire",
    "id": "run",
    "speed_m_s": 3.0,
    "clearance_m": 30.0,
}
MILL_ABOUT: dict[str, object] = {
    "node": "wander",
    "id": "mill-about",
    "radius_m": 6.0,
    "speed_m_s": 0.8,
    "seed": 7,
}


def an_evacuee(run: dict[str, object] = RUN) -> dict[str, object]:
    escape = {"node": "sequence", "id": "escape", "children": [SMELL_SMOKE, run]}
    return {"node": "selector", "id": "root", "children": [escape, MILL_ABOUT]}


EVACUEE = an_evacuee()

VEERING: dict[str, object] = {
    "node": "sequence",
    "children": [
        {"node": "idle", "s": 20.0},
        {"node": "set_wind", "from_deg": 300.0, "speed_m_s": 10.0, "gust_m_s": 3.0, "over_s": 30.0},
    ],
}


def a_lot_with_a_person() -> dict[str, object]:
    lot = load_presets(POC_ASSETS)["empty-lot"]
    person = {
        "kind": "person",
        "id": "evacuee-1",
        "position_enu": [10.0, 60.0, 0.0],
        "coat": "coat_orange",
        "skin": "skin",
    }
    return add_element(lot, person)


def a_windy_lot_with_a_person() -> dict[str, object]:
    return set_weather(
        a_lot_with_a_person(),
        rain_mm_h=0.0,
        fog_visibility_m=None,
        wind_from_deg=270.0,
        wind_speed_m_s=6.0,
        wind_gust_m_s=1.0,
    )


def test_a_person_is_given_a_tree_without_touching_the_original() -> None:
    # Given a lot with a person standing still
    lot = a_lot_with_a_person()

    # When the person is given an evacuee's tree
    edited = set_behaviour(lot, "evacuee-1", EVACUEE)

    # Then the edited scenario's person carries it, and the original is unchanged
    assert behaviour_of(edited, "evacuee-1") == EVACUEE
    assert behaviour_of(lot, "evacuee-1") is None
    validate_manifest(edited)


def test_the_wind_tree_lives_on_the_weathers_wind() -> None:
    # When the wind of a windy lot is given a tree that veers it
    edited = set_behaviour(a_windy_lot_with_a_person(), "wind", VEERING)

    # Then the wind carries the tree next to its starting values
    assert behaviour_of(edited, "wind") == VEERING
    assert wind_of(edited)["from_deg"] == 270.0
    assert wind_of(edited)["behaviour"] == VEERING


def test_the_wind_has_no_tree_before_the_scenario_has_weather() -> None:
    with pytest.raises(ScenarioInvalid, match="weather"):
        set_behaviour(a_lot_with_a_person(), "wind", VEERING)


def test_a_tree_for_an_unknown_target_is_refused() -> None:
    with pytest.raises(ScenarioInvalid, match="nobody"):
        set_behaviour(a_lot_with_a_person(), "nobody", EVACUEE)


def test_only_people_and_the_wind_take_trees() -> None:
    with pytest.raises(ScenarioInvalid, match="ground"):
        set_behaviour(a_lot_with_a_person(), "ground", EVACUEE)


@pytest.mark.parametrize(
    ("target", "tree", "reason"),
    [
        ("evacuee-1", {"node": "teleport", "enu": [0.0, 0.0]}, "teleport"),
        (
            "evacuee-1",
            {"node": "set_wind", "from_deg": 0.0, "speed_m_s": 5.0, "gust_m_s": 0.0, "over_s": 1.0},
            "set_wind",
        ),
        ("wind", {"node": "move_to", "enu": [1.0, 1.0], "speed_m_s": 1.0}, "move_to"),
        ("evacuee-1", {"node": "move_to", "enu": [1.0, 1.0], "speed_m_s": 0.0}, "speed_m_s"),
        ("evacuee-1", {"node": "selector", "children": []}, "children"),
        (
            "evacuee-1",
            {
                "node": "sequence",
                "children": [
                    {"node": "idle", "id": "a", "s": 1.0},
                    {"node": "idle", "id": "a", "s": 2.0},
                ],
            },
            "'a'",
        ),
        ("evacuee-1", {"node": "idle", "s": 1.0, "colour": "red"}, "colour"),
    ],
)
def test_an_invalid_tree_is_refused_with_its_reason(
    target: str, tree: dict[str, object], reason: str
) -> None:
    with pytest.raises(ScenarioInvalid, match=reason):
        set_behaviour(a_windy_lot_with_a_person(), target, tree)


def test_one_node_is_replaced_by_its_id_deep_in_the_tree() -> None:
    # Given a person with the evacuee's tree
    scenario = set_behaviour(a_lot_with_a_person(), "evacuee-1", EVACUEE)
    sprint = {"node": "flee_from_fire", "id": "run", "speed_m_s": 5.0, "clearance_m": 50.0}

    # When the agent makes the escape a sprint
    edited = update_behaviour_node(scenario, "evacuee-1", "run", sprint)

    # Then only that node changed
    assert behaviour_of(edited, "evacuee-1") == an_evacuee(run=sprint)


def test_updating_a_node_that_is_not_there_is_refused() -> None:
    scenario = set_behaviour(a_lot_with_a_person(), "evacuee-1", EVACUEE)

    with pytest.raises(ScenarioInvalid, match="sprint"):
        update_behaviour_node(scenario, "evacuee-1", "sprint", {"node": "idle", "s": 1.0})


def test_an_update_that_breaks_the_tree_is_refused() -> None:
    scenario = set_behaviour(a_lot_with_a_person(), "evacuee-1", EVACUEE)
    gust = {
        "node": "set_wind",
        "id": "run",
        "from_deg": 0.0,
        "speed_m_s": 5.0,
        "gust_m_s": 0.0,
        "over_s": 1.0,
    }

    with pytest.raises(ScenarioInvalid, match="set_wind"):
        update_behaviour_node(scenario, "evacuee-1", "run", gust)


def test_a_manifest_carrying_an_invalid_tree_is_refused() -> None:
    scenario = a_lot_with_a_person()
    elements = scenario["elements"]
    assert isinstance(elements, list)
    person = elements[-1]
    assert isinstance(person, dict)
    person["behaviour"] = {"node": "wander", "radius_m": -1.0, "speed_m_s": 1.0, "seed": 1}

    with pytest.raises(ScenarioInvalid, match="radius_m"):
        validate_manifest(scenario)


def test_the_evacuation_preset_is_the_wildfire_edge_with_people_and_a_veering_wind() -> None:
    # When the presets are loaded
    presets = load_presets(POC_ASSETS)
    evacuation = presets["wildfire-evacuation"]

    # Then it is the wildfire edge with three people who flee, and a wind that veers and builds
    people = person_ids(evacuation)
    assert len(people) == 3
    assert all(behaviour_of(evacuation, p) is not None for p in people)
    assert fire_ids(evacuation) == fire_ids(presets["wildfire-edge"])
    wind_tree = behaviour_of(evacuation, "wind")
    assert wind_tree is not None and "set_wind" in str(wind_tree)
    validate_manifest(evacuation)


def test_a_near_object_node_has_an_id_and_names_its_body_by_object() -> None:
    # Given a person whose tree watches a car through a node with an id
    watch = {"node": "near_object", "id": "watch-car", "object": "car-1", "within_m": 6.0}
    scenario = set_behaviour(
        a_lot_with_a_person(), "evacuee-1", {"node": "sequence", "children": [watch, MILL_ABOUT]}
    )

    # When the agent watches another car instead, by the node's id
    widened = {"node": "near_object", "id": "watch-car", "object": "car-2", "within_m": 4.0}
    edited = update_behaviour_node(scenario, "evacuee-1", "watch-car", widened)

    # Then only that node changed, and it still answers to its id
    assert behaviour_of(edited, "evacuee-1") == {
        "node": "sequence",
        "children": [widened, MILL_ABOUT],
    }
