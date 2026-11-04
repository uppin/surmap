"""Acceptance: the agent builds a wildfire scenario through its tools, and the station serves it.

Same harness as tests/test_sim_scenario_e2e.py: a scripted model drives a real agent turn on a real
socket over a real SQLite store; the page's request for the scenario is then made.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.messages.tool import ToolCall

from surmap.simulation.scenario_manifest import validate_manifest
from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call
from tests.sim_fakes import element_ids, fire_ids, vegetation_species, wind_of
from tests.test_sim_scenario_e2e import a_station

GOLDEN = Path(__file__).parent / "fixtures" / "sim_scenario" / "wildfire-edge.json"


def created(call_id: str, name: str, preset: str) -> ToolCall:
    return ToolCall(
        name="create_scenario", id=call_id, type="tool_call", args={"name": name, "preset": preset}
    )


def an_agent_lighting_a_ridge() -> ScriptedChatModel:
    stand = {
        "species": "species/pine.species.json",
        "position": {"east": -40.0, "north": 60.0, "up": 0.0},
        "size_east_m": 40.0,
        "size_north_m": 60.0,
        "density_per_100m2": 3.0,
        "seed": 11,
    }
    grass = {
        **stand,
        "id": "grass",
        "species": "species/dry_grass.species.json",
        "density_per_100m2": 30.0,
    }
    return ScriptedChatModel.replying(
        calling(created("c1", "Ridge fire", "empty-lot")),
        calling(
            tool_call(
                "add_element", "c2", scenario_id="ridge-fire", vegetation={**stand, "id": "pines"}
            )
        ),
        calling(tool_call("add_element", "c3", scenario_id="ridge-fire", vegetation=grass)),
        calling(
            tool_call(
                "set_weather",
                "c4",
                scenario_id="ridge-fire",
                wind_from_deg=270.0,
                wind_speed_m_s=6.0,
                wind_gust_m_s=2.0,
            )
        ),
        calling(
            tool_call(
                "add_fire",
                "c5",
                scenario_id="ridge-fire",
                id="front-1",
                ignition={"east": -58.0, "north": 60.0, "up": 0.0},
                start_s=2.0,
                spread_m_s=0.15,
                max_radius_m=35.0,
            )
        ),
        calling(created("c6", "Wildfire edge", "wildfire-edge")),
        answer("Ridge fire is lit; the wildfire-edge preset is ready too."),
    )


async def test_an_agent_turn_lights_a_fire_in_a_windy_pine_stand(tmp_path: Path) -> None:
    # Given the station with an agent scripted to build a ridge fire
    async with a_station(tmp_path, an_agent_lighting_a_ridge()) as station:
        # When the agent takes its turn and the page asks for the scenario
        await asyncio.to_thread(station.turn, "Light a grass fire upwind of a pine stand")
        status, body = await asyncio.to_thread(station.get, "/sim/assets/scenarios/ridge-fire.json")

    # Then the served scenario is valid, with the stand, the grass, a westerly and the fire
    assert status == 200
    manifest = json.loads(body)
    validate_manifest(manifest)
    assert element_ids(manifest) == ["ground", "pines", "grass"]
    assert vegetation_species(manifest) == {
        "species/pine.species.json",
        "species/dry_grass.species.json",
    }
    assert wind_of(manifest)["from_deg"] == 270.0
    assert fire_ids(manifest) == ["front-1"]


async def test_the_served_wildfire_edge_preset_is_the_golden_the_renderer_validates(
    tmp_path: Path,
) -> None:
    # Given the station after the agent created the wildfire-edge scenario
    async with a_station(tmp_path, an_agent_lighting_a_ridge()) as station:
        await asyncio.to_thread(station.turn, "Light a grass fire upwind of a pine stand")
        _, body = await asyncio.to_thread(station.get, "/sim/assets/scenarios/wildfire-edge.json")

    # Then it is the committed golden the Rust renderer's tests parse
    assert json.loads(body) == json.loads(GOLDEN.read_text(encoding="utf-8"))


async def test_the_shipped_effect_and_species_files_are_served_to_the_page(tmp_path: Path) -> None:
    # Given the station
    async with a_station(tmp_path, an_agent_lighting_a_ridge()) as station:
        # When the page asks for the declarative files a fire and a stand name
        flames, _ = await asyncio.to_thread(station.get, "/sim/assets/fx/flames.fx.json")
        pine, _ = await asyncio.to_thread(station.get, "/sim/assets/species/pine.species.json")

    # Then both come from the simulation's own assets
    assert (flames, pine) == (200, 200)
