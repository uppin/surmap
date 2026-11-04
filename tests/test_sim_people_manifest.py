"""The `person` element's look in the station: pose, height, facing and rig, and the preset."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from surmap.simulation.scenario_manifest import (
    ScenarioInvalid,
    add_element,
    behaviour_of,
    load_presets,
    validate_manifest,
)
from tests.sim_fakes import POC_ASSETS, people_of

GOLDEN = Path(__file__).parent / "fixtures" / "sim_scenario" / "earthquake-survivors.json"


def a_person(**fields: object) -> dict[str, object]:
    return {
        "kind": "person",
        "id": "p1",
        "position_enu": [-15.0, 31.0, 0.0],
        "coat": "coat_yellow",
        "skin": "skin",
        **fields,
    }


def a_block_with(person: dict[str, object]) -> dict[str, object]:
    return add_element(load_presets(POC_ASSETS)["earthquake-block"], person)


@pytest.mark.parametrize("pose", ["standing", "lying", "sitting", "waving"])
def test_a_person_may_take_each_pose(pose: str) -> None:
    validate_manifest(a_block_with(a_person(pose=pose, yaw_deg=30.0, height_m=1.68)))


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"pose": "dancing"}, "dancing"),
        ({"height_m": 3.0}, "height_m"),
        ({"height_m": 0.5}, "height_m"),
        ({"yaw_deg": "north"}, "yaw_deg"),
        ({"glb": "models/person.fbx"}, "person.fbx"),
        ({"glb": "/abs/person.glb"}, "/abs/person.glb"),
    ],
)
def test_a_person_the_renderer_would_refuse_is_refused_with_its_reason(
    fields: dict[str, object], reason: str
) -> None:
    with pytest.raises(ScenarioInvalid, match=f"p1.*{reason}|{reason}.*p1"):
        validate_manifest(a_block_with(a_person(**fields)))


def test_the_survivors_preset_has_people_lying_sitting_and_waving_and_rescuers_walking() -> None:
    presets = load_presets(POC_ASSETS)

    survivors = presets["earthquake-survivors"]

    people = people_of(survivors)
    poses = sorted(str(p.get("pose", "standing")) for p in people)
    assert poses == ["lying", "sitting", "standing", "standing", "waving"]
    rescuers = [p for p in people if p.get("pose", "standing") == "standing"]
    assert all(behaviour_of(survivors, str(r["id"])) is not None for r in rescuers)
    validate_manifest(survivors)


def test_the_survivors_preset_is_the_golden_the_renderer_parses() -> None:
    survivors = load_presets(POC_ASSETS)["earthquake-survivors"]

    assert survivors == json.loads(GOLDEN.read_text(encoding="utf-8"))
