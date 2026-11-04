"""The simulation tools — search, download, compose — over a real store and canned sources.

Handler tests with no model and no server: proto request in, proto response out, `ConnectError`
codes for a request the caller got wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import simulation_tools_pb2 as pb
from surmap.agent.tools.simulation_handlers import simulation_tool_handlers
from surmap.simulation.asset_sources import AmbientCg, AssetSource, PolyHaven, Sketchfab
from surmap.simulation.scenario_manifest import load_presets
from surmap.simulation.scenario_store import ScenarioStore
from tests.sim_fakes import POC_ASSETS, RecordingFetch, element_ids


def a_toolset(tmp_path: Path, *, token: str | None = "t") -> dict[str, object]:
    fetch = RecordingFetch()
    sources: dict[str, AssetSource] = {
        "polyhaven": PolyHaven(fetch),
        "ambientcg": AmbientCg(fetch),
        "sketchfab": Sketchfab(fetch, token=token),
    }
    store = ScenarioStore(
        db_path=tmp_path / "simulation.sqlite",
        library_dir=tmp_path / "library",
        presets=load_presets(POC_ASSETS),
    )
    return dict(simulation_tool_handlers(store, sources))


async def call(handlers: dict[str, object], rpc: str, request: object) -> object:
    handler = handlers[rpc]
    assert callable(handler)
    return await handler(request, None)


async def test_search_reports_each_hits_licence_verdict(tmp_path: Path) -> None:
    # Given the tools over the three sources
    tools = a_toolset(tmp_path)

    # When Sketchfab is searched for a burnt car
    found = await call(
        tools,
        "SearchAssets",
        pb.SearchAssetsRequest(query="burnt car", kind=pb.ASSET_KIND_MODEL, sources=["sketchfab"]),
    )

    # Then the hit carries its ref and an accepted CC BY verdict
    assert isinstance(found, pb.SearchAssetsResponse)
    assert [(h.ref, h.accepted, h.licence) for h in found.hits] == [
        ("sketchfab:3f1c0a", True, "CC Attribution")
    ]


async def test_a_downloaded_asset_reports_the_path_scenarios_use(tmp_path: Path) -> None:
    # Given the tools after a search
    tools = a_toolset(tmp_path)
    await call(
        tools,
        "SearchAssets",
        pb.SearchAssetsRequest(query="car", kind=pb.ASSET_KIND_MODEL, sources=["polyhaven"]),
    )

    # When the covered car is downloaded
    stored = await call(
        tools, "DownloadAsset", pb.DownloadAssetRequest(ref="polyhaven:covered_car")
    )

    # Then its entry path is in the library and it is listed
    assert isinstance(stored, pb.AssetResponse)
    assert stored.asset.entry_path == "library/polyhaven/covered_car/covered_car_2k.gltf"
    listed = await call(tools, "ListAssets", pb.ListAssetsRequest())
    assert isinstance(listed, pb.ListAssetsResponse)
    assert [a.ref for a in listed.assets] == ["polyhaven:covered_car"]


async def test_downloading_an_asset_never_searched_is_not_found(tmp_path: Path) -> None:
    # Given fresh tools
    tools = a_toolset(tmp_path)

    # Then a ref no search returned is NOT_FOUND
    with pytest.raises(ConnectError) as raised:
        await call(tools, "DownloadAsset", pb.DownloadAssetRequest(ref="polyhaven:unicorn"))
    assert raised.value.code == Code.NOT_FOUND


async def test_a_sketchfab_download_without_a_token_is_a_failed_precondition(
    tmp_path: Path,
) -> None:
    # Given the tools with no Sketchfab token, after finding the burnt car
    tools = a_toolset(tmp_path, token=None)
    await call(
        tools,
        "SearchAssets",
        pb.SearchAssetsRequest(query="burnt car", kind=pb.ASSET_KIND_MODEL, sources=["sketchfab"]),
    )

    # Then downloading it fails, naming the variable
    with pytest.raises(ConnectError) as raised:
        await call(tools, "DownloadAsset", pb.DownloadAssetRequest(ref="sketchfab:3f1c0a"))
    assert raised.value.code == Code.FAILED_PRECONDITION
    assert "SKETCHFAB_API_TOKEN" in raised.value.message


async def test_a_model_and_a_building_compose_a_new_version(tmp_path: Path) -> None:
    # Given an empty lot and the covered car in the library
    tools = a_toolset(tmp_path)
    await call(
        tools,
        "SearchAssets",
        pb.SearchAssetsRequest(query="car", kind=pb.ASSET_KIND_MODEL, sources=["polyhaven"]),
    )
    await call(tools, "DownloadAsset", pb.DownloadAssetRequest(ref="polyhaven:covered_car"))
    created = await call(
        tools, "CreateScenario", pb.CreateScenarioRequest(name="Lot", preset="empty-lot")
    )
    assert isinstance(created, pb.ScenarioResponse)
    scenario_id = created.scenario.id

    # When the car and a building are added
    await call(
        tools,
        "AddModel",
        pb.AddModelRequest(
            scenario_id=scenario_id,
            asset_ref="polyhaven:covered_car",
            position=pb.EnuPoint(east=4.0, north=10.0, up=0.0),
            yaw_deg=30.0,
            collider=pb.COLLIDER_BOX,
            ground_truth_kind="car",
            element_id="car-1",
        ),
    )
    added = await call(
        tools,
        "AddElement",
        pb.AddElementRequest(
            scenario_id=scenario_id,
            building=pb.BuildingElement(
                id="tower-1",
                material="ground",
                size=pb.EnuPoint(east=12.0, north=12.0, up=18.0),
                position=pb.EnuPoint(east=40.0, north=20.0, up=0.0),
            ),
        ),
    )

    # Then the scenario is at version 3 with both, and the page URL names it
    assert isinstance(added, pb.ScenarioResponse)
    manifest = json.loads(added.scenario.manifest_json)
    assert added.scenario.version == 3
    assert element_ids(manifest) == ["ground", "tower-1"]
    assert [m["glb"] for m in manifest["models"]] == [
        "library/polyhaven/covered_car/covered_car_2k.gltf"
    ]
    assert added.scenario.url == f"/sim/?scenario={scenario_id}"


async def test_an_element_with_an_unknown_material_is_invalid(tmp_path: Path) -> None:
    # Given an empty lot
    tools = a_toolset(tmp_path)
    created = await call(
        tools, "CreateScenario", pb.CreateScenarioRequest(name="Lot", preset="empty-lot")
    )
    assert isinstance(created, pb.ScenarioResponse)

    # Then a box of marble is INVALID_ARGUMENT, naming the material
    with pytest.raises(ConnectError) as raised:
        await call(
            tools,
            "AddElement",
            pb.AddElementRequest(
                scenario_id=created.scenario.id,
                box=pb.BoxElement(
                    id="plinth",
                    material="marble",
                    size=pb.EnuPoint(east=1.0, north=1.0, up=1.0),
                    position=pb.EnuPoint(east=0.0, north=0.0, up=0.0),
                ),
            ),
        )
    assert raised.value.code == Code.INVALID_ARGUMENT
    assert "marble" in raised.value.message


async def test_an_unknown_scenario_is_not_found(tmp_path: Path) -> None:
    # Then asking for a scenario that does not exist is NOT_FOUND
    with pytest.raises(ConnectError) as raised:
        await call(a_toolset(tmp_path), "GetScenario", pb.GetScenarioRequest(scenario_id="nowhere"))
    assert raised.value.code == Code.NOT_FOUND


async def test_a_vehicle_with_a_drive_is_added_as_a_new_version(tmp_path: Path) -> None:
    # Given the earthquake block
    tools = a_toolset(tmp_path)
    created = await call(
        tools, "CreateScenario", pb.CreateScenarioRequest(name="Block", preset="earthquake-block")
    )
    assert isinstance(created, pb.ScenarioResponse)
    drive = {"node": "follow_path", "enu": [[-2.5, 120.0]], "speed_m_s": 8.0}

    # When a bus that drives up the avenue is added
    added = await call(
        tools,
        "AddElement",
        pb.AddElementRequest(
            scenario_id=created.scenario.id,
            vehicle=pb.VehicleElement(
                id="bus-1",
                vehicle_class="bus",
                position=pb.EnuPoint(east=-2.5, north=-40.0, up=0.0),
                yaw_deg=90.0,
                behaviour_json=json.dumps(drive),
            ),
        ),
    )

    # Then the new version holds the bus, its pose and its drive
    assert isinstance(added, pb.ScenarioResponse)
    manifest = json.loads(added.scenario.manifest_json)
    buses = [e for e in manifest["elements"] if e["id"] == "bus-1"]
    assert buses == [
        {
            "kind": "vehicle",
            "id": "bus-1",
            "class": "bus",
            "position_enu": [-2.5, -40.0, 0.0],
            "yaw_deg": 90.0,
            "behaviour": drive,
        }
    ]


async def test_a_vehicle_of_an_unknown_class_is_invalid(tmp_path: Path) -> None:
    # Given the earthquake block
    tools = a_toolset(tmp_path)
    created = await call(
        tools, "CreateScenario", pb.CreateScenarioRequest(name="Block", preset="earthquake-block")
    )
    assert isinstance(created, pb.ScenarioResponse)

    # Then a hovercraft is INVALID_ARGUMENT, naming the class
    with pytest.raises(ConnectError) as raised:
        await call(
            tools,
            "AddElement",
            pb.AddElementRequest(
                scenario_id=created.scenario.id,
                vehicle=pb.VehicleElement(
                    id="hover-1",
                    vehicle_class="hovercraft",
                    position=pb.EnuPoint(east=0.0, north=0.0, up=0.0),
                ),
            ),
        )
    assert raised.value.code == Code.INVALID_ARGUMENT
    assert "hovercraft" in raised.value.message
