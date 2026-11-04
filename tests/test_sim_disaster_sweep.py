"""The sim-disaster-2 sweep: fire floors from districts, recorded dynamics end to end."""

from __future__ import annotations

from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import simulation_tools_pb2 as pb
from surmap.agent.tools.simulation_handlers import simulation_tool_handlers
from surmap.simulation.bevy_capture import BevyCapture, load_bevy_capture
from surmap.simulation.building_presets import add_building_fire
from surmap.simulation.scenario_manifest import (
    ScenarioInvalid,
    add_element,
    load_presets,
    set_district,
)
from surmap.simulation.scenario_store import ScenarioStore
from tests.sim_fakes import POC_ASSETS, building_fire_ids

DYNAMICS = Path(__file__).parent / "fixtures" / "bevy_capture_dynamics"


def a_downtown_tower_without_floors() -> dict[str, object]:
    lot = load_presets(POC_ASSETS)["empty-lot"]
    core = set_district(
        lot, "core", "downtown", position_enu=(0.0, 0.0, 0.0), size_m=(120.0, 80.0), seed=4
    )
    tower = {
        "kind": "building",
        "id": "tower-2",
        "size_m": [18.0, 18.0, 42.0],
        "position_enu": [30.0, 10.0, 0.0],
    }
    return add_element(core, tower)


def test_a_fire_floor_is_checked_against_the_floors_the_district_gives() -> None:
    # Given a 42 m tower in downtown (3.6 m floors: 11 of them), with no floors of its own
    tower = a_downtown_tower_without_floors()

    # When fires are lit on its top floor and one floor above
    top = add_building_fire(tower, "blaze-1", building="tower-2", floor=10, assets_dir=POC_ASSETS)

    # Then the top floor burns and the floor that does not exist is refused
    assert building_fire_ids(top) == ["blaze-1"]
    with pytest.raises(ScenarioInvalid, match="floor"):
        add_building_fire(tower, "blaze-2", building="tower-2", floor=11, assets_dir=POC_ASSETS)


async def test_the_tool_refuses_a_floor_past_the_districts_count(tmp_path: Path) -> None:
    store = ScenarioStore(
        tmp_path / "s.sqlite", tmp_path / "lib", load_presets(POC_ASSETS), POC_ASSETS
    )
    scenario_id = store.create_scenario("Block", "empty-lot").id
    store.save(scenario_id, a_downtown_tower_without_floors())
    handler = dict(simulation_tool_handlers(store, {}))["AddBuildingFire"]
    request = pb.AddBuildingFireRequest(
        scenario_id=scenario_id, id="blaze-1", building_id="tower-2", floor=11
    )

    with pytest.raises(ConnectError) as raised:
        await handler(request, None)
    assert raised.value.code == Code.INVALID_ARGUMENT


def recorded(name: str) -> BevyCapture:
    return load_bevy_capture(DYNAMICS / name)


def inside(point: tuple[float, float], polygon: tuple[tuple[float, float], ...]) -> bool:
    x, y = point
    hits = 0
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hits += 1
    return hits % 2 == 1


def test_a_recorded_evacuation_keeps_every_person_out_of_the_fire() -> None:
    # Given a real recording of the wildfire-evacuation scenario
    capture = recorded("evacuation")

    # Then every frame has the fire front, three people and the wind, and nobody stands in the fire
    assert capture.fire_perimeters and capture.object_tracks and capture.wind
    for t_ns, people in capture.object_tracks.items():
        assert len(people) == 3, t_ns
        for front in capture.fire_perimeters.get(t_ns, {}).values():
            assert not any(inside((p.x, p.y), front) for p in people.values()), t_ns


def test_a_recorded_blaze_climbs_and_never_unburns() -> None:
    # Given a real recording of the downtown-blaze scenario
    capture = recorded("blaze")

    # Then the tower's burning floors grow from its ignition floor and burnt floors never return
    frames = [capture.building_fires[t] for t in sorted(capture.building_fires)]
    assert frames, "the recorder wrote building_fires.jsonl"
    burnt: set[int] = set()
    for frame in frames:
        burning_now, burnt_now = frame.get("tower-1", ((), ()))
        assert burnt <= set(burnt_now)
        assert not set(burning_now) & set(burnt_now)
        burnt = set(burnt_now)
    assert 3 in frames[-1]["tower-1"][0] + frames[-1]["tower-1"][1]


def test_a_district_preset_the_station_cannot_read_leaves_the_floor_to_the_renderer(
    tmp_path: Path,
) -> None:
    # Given the downtown tower, its district preset missing from the assets the station reads
    tower = a_downtown_tower_without_floors()

    # When a fire is lit on a floor only a guessed floor height would refuse
    lit = add_building_fire(tower, "blaze-1", building="tower-2", floor=14, assets_dir=tmp_path)

    # Then the station invents no floor count; the renderer checks it against the real preset
    assert building_fire_ids(lit) == ["blaze-1"]
