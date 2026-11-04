"""The set_map_floor agent tool over fake tiles and a real store."""

from __future__ import annotations

import pytest

from surmap.simulation.map_floor import GeoBBox, InMemoryTileSource, wgs84_to_enu
from surmap.simulation.scenario_manifest import load_presets, validate_manifest
from tests.sim_fakes import POC_ASSETS

VILNIUS = GeoBBox(sw_lat=54.0, sw_lon=25.0, ne_lat=54.001, ne_lon=25.002)


async def test_set_map_floor_tool_stitches_the_floor_and_reports_the_enu_origin(
    tmp_path: object,
) -> None:
    # Given a scenario and the simulation tools over fake tiles
    from pathlib import Path

    from surmap.agent.proto import simulation_tools_pb2 as pb
    from surmap.agent.tools.simulation_handlers import simulation_tool_handlers
    from surmap.simulation.scenario_store import ScenarioStore

    assert isinstance(tmp_path, Path)
    store = ScenarioStore(
        db_path=tmp_path / "simulation.sqlite",
        library_dir=tmp_path / "library",
        presets=load_presets(POC_ASSETS),
    )
    tools = dict(simulation_tool_handlers(store, {}, tile_source=InMemoryTileSource()))
    created = await tools["CreateScenario"](
        pb.CreateScenarioRequest(name="Vilnius yard", preset="empty-lot"), None
    )

    # When the agent bases it on the Vilnius bbox
    floored = await tools["SetMapFloor"](
        pb.SetMapFloorRequest(
            scenario_id=created.scenario.id,
            sw_lat=VILNIUS.sw_lat,
            sw_lon=VILNIUS.sw_lon,
            ne_lat=VILNIUS.ne_lat,
            ne_lon=VILNIUS.ne_lon,
        ),
        None,
    )

    # Then the floor is reported with its ENU origin, and the texture is in the library
    assert isinstance(floored, pb.MapFloorResponse)
    assert floored.centre_lat == pytest.approx(54.0005)
    assert floored.size_north_m == pytest.approx(111.32)
    assert floored.texture.startswith("library/map-floor/")
    assert (tmp_path / floored.texture).is_file()
    manifest = store.scenario(created.scenario.id).manifest
    assert isinstance(manifest["map_floor"], dict)


async def test_the_agent_places_a_building_on_the_map_floor_by_gps(tmp_path: object) -> None:
    # Given a scenario based on the Vilnius bbox, and a target GPS point inside it
    from pathlib import Path

    from surmap.agent.proto import simulation_tools_pb2 as pb
    from surmap.agent.tools.simulation_handlers import simulation_tool_handlers
    from surmap.simulation.scenario_store import ScenarioStore

    assert isinstance(tmp_path, Path)
    store = ScenarioStore(
        db_path=tmp_path / "simulation.sqlite",
        library_dir=tmp_path / "library",
        presets=load_presets(POC_ASSETS),
    )
    tools = dict(simulation_tool_handlers(store, {}, tile_source=InMemoryTileSource()))
    created = await tools["CreateScenario"](
        pb.CreateScenarioRequest(name="Vilnius yard", preset="empty-lot"), None
    )
    floored = await tools["SetMapFloor"](
        pb.SetMapFloorRequest(
            scenario_id=created.scenario.id,
            sw_lat=VILNIUS.sw_lat,
            sw_lon=VILNIUS.sw_lon,
            ne_lat=VILNIUS.ne_lat,
            ne_lon=VILNIUS.ne_lon,
        ),
        None,
    )
    east, north = wgs84_to_enu(54.0008, 25.0015, floored.centre_lat, floored.centre_lon)

    # When the agent adds a building at that ENU point
    await tools["AddElement"](
        pb.AddElementRequest(
            scenario_id=created.scenario.id,
            building=pb.BuildingElement(
                id="depot",
                material="facade",
                size=pb.EnuPoint(east=10.0, north=8.0, up=6.0),
                position=pb.EnuPoint(east=east, north=north, up=0.0),
            ),
        ),
        None,
    )

    # Then the manifest holds the floor and the building north-east of the origin
    manifest = store.scenario(created.scenario.id).manifest
    validate_manifest(manifest)
    elements = manifest["elements"]
    assert isinstance(elements, list)
    depot = next(e for e in elements if isinstance(e, dict) and e.get("id") == "depot")
    assert depot["position_enu"][0] > 0 and depot["position_enu"][1] > 0
