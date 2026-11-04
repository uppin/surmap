"""The set_map_floor agent tool over fake tiles and a real store."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from surmap.simulation.scenario_store import ScenarioStore

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


async def test_geo_to_enu_converts_through_the_tool_not_the_test(tmp_path: object) -> None:
    # Given a floored scenario
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
    await tools["SetMapFloor"](
        pb.SetMapFloorRequest(
            scenario_id=created.scenario.id,
            sw_lat=VILNIUS.sw_lat,
            sw_lon=VILNIUS.sw_lon,
            ne_lat=VILNIUS.ne_lat,
            ne_lon=VILNIUS.ne_lon,
        ),
        None,
    )

    # When the agent converts a GPS point through the tool
    converted = await tools["GeoToEnu"](
        pb.GeoToEnuRequest(scenario_id=created.scenario.id, lat=54.0008, lon=25.0015), None
    )

    # Then it gets ENU metres from the floor centre and an inside-floor flag
    assert isinstance(converted, pb.GeoToEnuResponse)
    assert converted.position.east == pytest.approx(32.7, abs=0.5)
    assert converted.position.north == pytest.approx(33.4, abs=0.5)
    assert converted.inside_floor is True

    # And the reverse conversion lands back on the GPS point
    back = await tools["EnuToGeo"](
        pb.EnuToGeoRequest(
            scenario_id=created.scenario.id,
            position=pb.EnuPoint(
                east=converted.position.east, north=converted.position.north, up=0.0
            ),
        ),
        None,
    )
    assert back.lat == pytest.approx(54.0008, abs=1e-5)
    assert back.lon == pytest.approx(25.0015, abs=1e-5)


async def test_clear_map_floor_tool_removes_the_floor_and_restores_ground(tmp_path: object) -> None:
    # Given a floored scenario (as above, via the tool helper below)
    tools, store, scenario_id = await _floored_scenario(tmp_path)

    # When the agent clears the floor
    from surmap.agent.proto import simulation_tools_pb2 as pb

    await tools["ClearMapFloor"](pb.ClearMapFloorRequest(scenario_id=scenario_id), None)

    # Then the manifest has no floor and the ground box is back
    manifest = store.scenario(scenario_id).manifest
    assert "map_floor" not in manifest
    elements = manifest.get("elements")
    assert isinstance(elements, list)
    assert "ground" in [e.get("id") for e in elements if isinstance(e, dict)]


async def _floored_scenario(
    tmp_path: object,
) -> tuple[dict[str, Callable[..., Awaitable[object]]], ScenarioStore, str]:
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
    await tools["SetMapFloor"](
        pb.SetMapFloorRequest(
            scenario_id=created.scenario.id,
            sw_lat=VILNIUS.sw_lat,
            sw_lon=VILNIUS.sw_lon,
            ne_lat=VILNIUS.ne_lat,
            ne_lon=VILNIUS.ne_lon,
        ),
        None,
    )
    return tools, store, created.scenario.id


async def test_resetting_the_same_floor_does_not_warn_about_reanchoring(tmp_path: object) -> None:
    # Given a scenario floored on the Vilnius bbox, with a building placed on it
    tools, store, scenario_id = await _floored_scenario(tmp_path)
    from surmap.agent.proto import simulation_tools_pb2 as pb

    await tools["AddElement"](
        pb.AddElementRequest(
            scenario_id=scenario_id,
            building=pb.BuildingElement(
                id="depot",
                material="facade",
                size=pb.EnuPoint(east=10.0, north=8.0, up=6.0),
                position=pb.EnuPoint(east=10.0, north=10.0, up=0.0),
            ),
        ),
        None,
    )

    # When the same bbox is set again
    reset = await tools["SetMapFloor"](
        pb.SetMapFloorRequest(
            scenario_id=scenario_id,
            sw_lat=VILNIUS.sw_lat, sw_lon=VILNIUS.sw_lon,
            ne_lat=VILNIUS.ne_lat, ne_lon=VILNIUS.ne_lon,
        ),
        None,
    )

    # Then nothing moved, so there is nothing to warn about
    assert isinstance(reset, pb.MapFloorResponse)
    assert list(reset.warnings) == []


async def test_a_non_osm_tile_source_adds_no_osm_credit(tmp_path: object) -> None:
    # Given a scenario floored through the in-memory source (not OpenStreetMap)
    _, store, scenario_id = await _floored_scenario(tmp_path)

    # Then its credits do not claim OpenStreetMap
    credits = store.scenario(scenario_id).credits
    assert not any("OpenStreetMap" in credit.line() for credit in credits)
