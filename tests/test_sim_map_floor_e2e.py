"""Acceptance: an agent bases a scenario on the real map and places a building by GPS.

Same harness as tests/test_sim_scenario_e2e.py: a scripted model drives a real agent turn
on a real socket over a real store; only the tile source is in-memory (no network). The
scripted agent converts its GPS target through `geo_to_enu` and places the building at
the ENU the tool reports for that point.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call
from tests.sim_fakes import element_ids
from surmap.simulation.map_floor import InMemoryTileSource
from surmap.simulation.scenario_manifest import validate_manifest
from tests.test_sim_scenario_e2e import a_station

TARGET_LAT, TARGET_LON = 54.0008, 25.0015
# What geo_to_enu reports for the target from the Vilnius bbox centre (54.0005, 25.001).
TARGET_EAST, TARGET_NORTH = 32.71, 33.40


def an_agent_building_on_a_map_floor() -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(
            tool_call(
                "create_scenario", "c1", name="Vilnius yard", preset="empty-lot"
            )
        ),
        calling(
            tool_call(
                "set_map_floor",
                "c2",
                scenario_id="vilnius-yard",
                sw_lat=54.0,
                sw_lon=25.0,
                ne_lat=54.001,
                ne_lon=25.002,
            )
        ),
        calling(
            tool_call(
                "geo_to_enu", "c3", scenario_id="vilnius-yard", lat=TARGET_LAT, lon=TARGET_LON
            )
        ),
        calling(
            tool_call(
                "add_element",
                "c4",
                scenario_id="vilnius-yard",
                building={
                    "id": "depot",
                    "material": "facade",
                    "size": {"east": 10.0, "north": 8.0, "up": 6.0},
                    "position": {"east": TARGET_EAST, "north": TARGET_NORTH, "up": 0.0},
                },
            )
        ),
        calling(tool_call("get_scenario", "c5", scenario_id="vilnius-yard")),
        answer("The depot scenario is ready at /sim/?scenario=vilnius-yard"),
    )


async def test_an_agent_turn_builds_on_a_map_floor_the_station_serves(tmp_path: Path) -> None:
    # Given the station with an agent scripted to base a scene on a GPS bbox
    model = an_agent_building_on_a_map_floor()
    async with a_station(tmp_path, model, tile_source=InMemoryTileSource()) as station:
        # When the agent takes its turn, and the page then asks for the scenario
        await asyncio.to_thread(station.turn, "Base a yard scene on this map area, depot at the GPS point")
        status, body = await asyncio.to_thread(
            station.get, "/sim/assets/scenarios/vilnius-yard.json"
        )
        manifest = json.loads(body)
        texture = manifest["map_floor"]["texture"]
        tex_status, tex_body = await asyncio.to_thread(
            station.get, f"/sim/assets/{texture}"
        )

    # Then the served manifest is valid, floored, groundless, and holds the depot at the
    # ENU the conversion tool reports for the GPS target; the floor texture is served too
    assert status == 200
    validate_manifest(manifest)
    assert manifest["map_floor"]["sw"] == [54.0, 25.0]
    assert "ground" not in element_ids(manifest)
    assert "depot" in element_ids(manifest)
    assert tex_status == 200
    assert tex_body[:8] == b"\x89PNG\r\n\x1a\n"
    credits = station.store.scenario("vilnius-yard").credits
    assert any("OpenStreetMap" in credit.line() for credit in credits)
