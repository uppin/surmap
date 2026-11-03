"""The weather, fire and vegetation tools over a real store (no model, no server)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import simulation_tools_pb2 as pb
from surmap.agent.tools.simulation_handlers import simulation_tool_handlers
from surmap.simulation.scenario_manifest import load_presets
from surmap.simulation.scenario_store import ScenarioStore
from tests.sim_fakes import POC_ASSETS, element_ids, fire_ids, wind_of


def tools_with_a_lot(tmp_path: Path) -> tuple[dict[str, object], str]:
    store = ScenarioStore(tmp_path / "s.sqlite", tmp_path / "library", load_presets(POC_ASSETS))
    handlers = dict(simulation_tool_handlers(store, {}))
    scenario_id = store.create_scenario("Edge", "empty-lot").id
    return handlers, scenario_id


async def call(handlers: dict[str, object], rpc: str, request: object) -> pb.ScenarioResponse:
    handler = handlers[rpc]
    assert callable(handler)
    response = await handler(request, None)
    assert isinstance(response, pb.ScenarioResponse)
    return response


def manifest_of(response: pb.ScenarioResponse) -> dict[str, object]:
    loaded: dict[str, object] = json.loads(response.scenario.manifest_json)
    return loaded


async def test_set_weather_declares_the_one_wind(tmp_path: Path) -> None:
    # Given an empty lot
    tools, scenario_id = tools_with_a_lot(tmp_path)

    # When the agent sets a 6 m/s westerly with gusts
    response = await call(
        tools,
        "SetWeather",
        pb.SetWeatherRequest(
            scenario_id=scenario_id, wind_from_deg=270.0, wind_speed_m_s=6.0, wind_gust_m_s=2.0
        ),
    )

    # Then the scenario's wind is that westerly
    assert wind_of(manifest_of(response)) == {"from_deg": 270.0, "speed_m_s": 6.0, "gust_m_s": 2.0}


async def test_a_fire_is_added_then_removed(tmp_path: Path) -> None:
    # Given an empty lot with a fire
    tools, scenario_id = tools_with_a_lot(tmp_path)
    lit = await call(
        tools,
        "AddFire",
        pb.AddFireRequest(
            scenario_id=scenario_id,
            id="front-1",
            ignition=pb.EnuPoint(east=-20.0, north=60.0, up=0.0),
            start_s=2.0,
            spread_m_s=0.15,
            max_radius_m=35.0,
        ),
    )

    # When it is removed
    out = await call(
        tools, "RemoveFire", pb.RemoveFireRequest(scenario_id=scenario_id, fire_id="front-1")
    )

    # Then the versions record both
    assert fire_ids(manifest_of(lit)) == ["front-1"]
    assert fire_ids(manifest_of(out)) == []
    assert out.scenario.version == lit.scenario.version + 1


async def test_a_fire_that_cannot_spread_is_invalid(tmp_path: Path) -> None:
    tools, scenario_id = tools_with_a_lot(tmp_path)

    with pytest.raises(ConnectError) as raised:
        await call(
            tools,
            "AddFire",
            pb.AddFireRequest(
                scenario_id=scenario_id,
                id="f",
                ignition=pb.EnuPoint(),
                spread_m_s=0.0,
                max_radius_m=5.0,
            ),
        )
    assert raised.value.code == Code.INVALID_ARGUMENT


async def test_a_pine_stand_is_planted_through_add_element(tmp_path: Path) -> None:
    # Given an empty lot
    tools, scenario_id = tools_with_a_lot(tmp_path)

    # When pines are planted
    response = await call(
        tools,
        "AddElement",
        pb.AddElementRequest(
            scenario_id=scenario_id,
            vegetation=pb.VegetationElement(
                id="pines-west",
                species="species/pine.species.json",
                position=pb.EnuPoint(east=-40.0, north=60.0, up=0.0),
                size_east_m=40.0,
                size_north_m=60.0,
                density_per_100m2=3.0,
                seed=11,
            ),
        ),
    )

    # Then the stand is an element of the scenario
    assert element_ids(manifest_of(response)) == ["ground", "pines-west"]
