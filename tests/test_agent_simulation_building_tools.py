"""The building preset, district and building-fire tools over a real store (no model, no server)."""

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
from tests.sim_fakes import POC_ASSETS, building, building_fire_ids, district_ids


def tools_on_a_lot(tmp_path: Path) -> tuple[dict[str, object], str]:
    store = ScenarioStore(tmp_path / "s.sqlite", tmp_path / "library", load_presets(POC_ASSETS))
    handlers: dict[str, object] = dict(simulation_tool_handlers(store, {}))
    return handlers, store.create_scenario("Block", "empty-lot").id


async def call(handlers: dict[str, object], rpc: str, request: object) -> object:
    handler = handlers[rpc]
    assert callable(handler)
    response: object = await handler(request, None)
    return response


async def edit(handlers: dict[str, object], rpc: str, request: object) -> dict[str, object]:
    response = await call(handlers, rpc, request)
    assert isinstance(response, pb.ScenarioResponse)
    manifest: dict[str, object] = json.loads(response.scenario.manifest_json)
    return manifest


async def a_downtown_tower(handlers: dict[str, object], scenario_id: str) -> dict[str, object]:
    await edit(
        handlers,
        "SetDistrict",
        pb.SetDistrictRequest(
            scenario_id=scenario_id,
            id="core",
            preset="downtown",
            centre=pb.EnuPoint(),
            size_east_m=120.0,
            size_north_m=80.0,
            seed=4,
        ),
    )
    return await edit(
        handlers,
        "AddElement",
        pb.AddElementRequest(
            scenario_id=scenario_id,
            building=pb.BuildingElement(
                id="tower-2",
                size=pb.EnuPoint(east=18.0, north=18.0, up=42.0),
                position=pb.EnuPoint(east=30.0, north=10.0),
            ),
        ),
    )


async def test_the_presets_are_listed_by_overture_name(tmp_path: Path) -> None:
    tools, _ = tools_on_a_lot(tmp_path)

    presets = await call(tools, "ListBuildingPresets", pb.ListBuildingPresetsRequest())

    assert isinstance(presets, pb.BuildingPresetsResponse)
    assert {"brick", "glass", "plaster"} <= set(presets.facades)
    assert {"roof_tiles", "slate", "solar_panels"} <= set(presets.roofs)
    assert "downtown" in presets.districts


async def test_a_tower_in_a_district_is_styled_as_glass(tmp_path: Path) -> None:
    # Given a tower in a downtown district, with no material of its own
    tools, scenario_id = tools_on_a_lot(tmp_path)
    placed = await a_downtown_tower(tools, scenario_id)

    # When the agent makes it a 12-floor glass tower with a metal roof
    styled = await edit(
        tools,
        "StyleBuilding",
        pb.StyleBuildingRequest(
            scenario_id=scenario_id,
            building_id="tower-2",
            facade="glass",
            roof="metal",
            floors=12,
            glazing="curtain_wall",
        ),
    )

    # Then the district stays, and the tower carries its own style
    assert district_ids(placed) == ["core"] and "material" not in building(placed, "tower-2")
    tower = building(styled, "tower-2")
    assert (tower["facade"], tower["roof"], tower["floors"]) == ("glass", "metal", 12)
    assert tower["glazing"] == {"kind": "curtain_wall"}


async def test_a_building_fire_is_lit_then_put_out(tmp_path: Path) -> None:
    tools, scenario_id = tools_on_a_lot(tmp_path)
    await a_downtown_tower(tools, scenario_id)
    await edit(
        tools,
        "StyleBuilding",
        pb.StyleBuildingRequest(scenario_id=scenario_id, building_id="tower-2", floors=12),
    )

    lit = await edit(
        tools,
        "AddBuildingFire",
        pb.AddBuildingFireRequest(
            scenario_id=scenario_id, id="blaze-1", building_id="tower-2", floor=3, start_s=5.0
        ),
    )
    out = await edit(
        tools,
        "RemoveBuildingFire",
        pb.RemoveBuildingFireRequest(scenario_id=scenario_id, fire_id="blaze-1"),
    )

    assert (building_fire_ids(lit), building_fire_ids(out)) == (["blaze-1"], [])


async def test_a_district_removed_from_under_its_buildings_is_invalid(tmp_path: Path) -> None:
    tools, scenario_id = tools_on_a_lot(tmp_path)
    await a_downtown_tower(tools, scenario_id)

    with pytest.raises(ConnectError) as raised:
        await edit(
            tools,
            "RemoveDistrict",
            pb.RemoveDistrictRequest(scenario_id=scenario_id, district_id="core"),
        )
    assert raised.value.code == Code.INVALID_ARGUMENT


@pytest.mark.parametrize(
    "request_",
    [
        pb.StyleBuildingRequest(building_id="tower-2", facade="marble"),
        pb.StyleBuildingRequest(building_id="tower-2", roof_shape="dome"),
        pb.StyleBuildingRequest(building_id="ground", facade="brick"),
    ],
)
async def test_a_style_that_cannot_render_is_invalid(
    tmp_path: Path, request_: pb.StyleBuildingRequest
) -> None:
    tools, scenario_id = tools_on_a_lot(tmp_path)
    await a_downtown_tower(tools, scenario_id)
    request_.scenario_id = scenario_id

    with pytest.raises(ConnectError) as raised:
        await edit(tools, "StyleBuilding", request_)
    assert raised.value.code == Code.INVALID_ARGUMENT
