"""Acceptance: the agent styles a district and a tower, sets it alight; the station serves it.

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
from tests.sim_fakes import building, building_fire_ids, district_ids
from tests.test_sim_scenario_e2e import a_station

GOLDEN = Path(__file__).parent / "fixtures" / "sim_scenario" / "downtown-blaze.json"


def created(call_id: str, name: str, preset: str) -> ToolCall:
    return ToolCall(
        name="create_scenario", id=call_id, type="tool_call", args={"name": name, "preset": preset}
    )


def an_agent_setting_a_tower_alight() -> ScriptedChatModel:
    tower = {
        "id": "tower-2",
        "size": {"east": 18.0, "north": 18.0, "up": 42.0},
        "position": {"east": 30.0, "north": 10.0, "up": 0.0},
    }
    return ScriptedChatModel.replying(
        calling(tool_call("list_building_presets", "c1")),
        calling(created("c2", "Tower fire", "empty-lot")),
        calling(
            tool_call(
                "set_district",
                "c3",
                scenario_id="tower-fire",
                id="core",
                preset="downtown",
                centre={"east": 0.0, "north": 0.0, "up": 0.0},
                size_east_m=120.0,
                size_north_m=80.0,
                seed=4,
            )
        ),
        calling(tool_call("add_element", "c4", scenario_id="tower-fire", building=tower)),
        calling(
            tool_call(
                "style_building",
                "c5",
                scenario_id="tower-fire",
                building_id="tower-2",
                facade="glass",
                roof="metal",
                floors=12,
            )
        ),
        calling(
            tool_call(
                "add_building_fire",
                "c6",
                scenario_id="tower-fire",
                id="blaze-1",
                building_id="tower-2",
                floor=3,
                start_s=5.0,
            )
        ),
        calling(created("c7", "Downtown blaze", "downtown-blaze")),
        answer("The glass tower is burning from its third floor."),
    )


async def test_an_agent_turn_sets_a_downtown_glass_tower_alight(tmp_path: Path) -> None:
    # Given the station with an agent scripted to set a tower alight
    async with a_station(tmp_path, an_agent_setting_a_tower_alight()) as station:
        # When the agent takes its turn and the page asks for the scenario
        await asyncio.to_thread(
            station.turn, "Set a downtown glass tower alight on its third floor"
        )
        status, body = await asyncio.to_thread(station.get, "/sim/assets/scenarios/tower-fire.json")

    # Then the served scenario is valid: the district, the glass tower and its fire
    assert status == 200
    manifest = json.loads(body)
    validate_manifest(manifest)
    assert district_ids(manifest) == ["core"]
    assert building(manifest, "tower-2")["facade"] == "glass"
    assert building_fire_ids(manifest) == ["blaze-1"]


async def test_the_served_downtown_blaze_preset_is_the_golden_the_renderer_validates(
    tmp_path: Path,
) -> None:
    async with a_station(tmp_path, an_agent_setting_a_tower_alight()) as station:
        await asyncio.to_thread(
            station.turn, "Set a downtown glass tower alight on its third floor"
        )
        _, body = await asyncio.to_thread(station.get, "/sim/assets/scenarios/downtown-blaze.json")

    assert json.loads(body) == json.loads(GOLDEN.read_text(encoding="utf-8"))


async def test_the_preset_files_are_served_to_the_page(tmp_path: Path) -> None:
    async with a_station(tmp_path, an_agent_setting_a_tower_alight()) as station:
        facade, _ = await asyncio.to_thread(
            station.get, "/sim/assets/building/facades/glass.facade.json"
        )
        district, _ = await asyncio.to_thread(
            station.get, "/sim/assets/building/districts/downtown.district.json"
        )
        tuning, _ = await asyncio.to_thread(station.get, "/sim/assets/building/fire.json")

    assert (facade, district, tuning) == (200, 200, 200)
