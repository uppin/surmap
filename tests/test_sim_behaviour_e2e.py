"""Acceptance: the agent gives people and the wind behaviour trees, and the station serves them.

Same harness as tests/test_sim_scenario_e2e.py: a scripted model drives a real agent turn on a real
socket over a real SQLite store; the page's request for the scenario is then made.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.messages.tool import ToolCall

from surmap.simulation.scenario_manifest import behaviour_of, validate_manifest
from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call
from tests.test_sim_scenario_e2e import a_station

GOLDEN = Path(__file__).parent / "fixtures" / "sim_scenario" / "wildfire-evacuation.json"

RUN: dict[str, object] = {
    "node": "flee_from_fire",
    "id": "run",
    "speed_m_s": 3.0,
    "clearance_m": 30.0,
}


def fleeing(run: dict[str, object] = RUN) -> dict[str, object]:
    escape = {"node": "sequence", "children": [{"node": "near_fire", "within_m": 20.0}, run]}
    return {
        "node": "selector",
        "children": [escape, {"node": "wander", "radius_m": 6.0, "speed_m_s": 0.8, "seed": 7}],
    }


FLEE = fleeing()
SPRINT: dict[str, object] = {
    "node": "flee_from_fire",
    "id": "run",
    "speed_m_s": 4.5,
    "clearance_m": 40.0,
}
VEER = {
    "node": "sequence",
    "children": [
        {"node": "idle", "s": 20.0},
        {"node": "set_wind", "from_deg": 300.0, "speed_m_s": 10.0, "gust_m_s": 3.0, "over_s": 30.0},
    ],
}


def created(call_id: str, name: str, preset: str) -> ToolCall:
    return ToolCall(
        name="create_scenario", id=call_id, type="tool_call", args={"name": name, "preset": preset}
    )


def an_agent_running_an_evacuation_drill() -> ScriptedChatModel:
    hiker = {
        "id": "hiker",
        "position": {"east": 10.0, "north": 60.0, "up": 0.0},
        "coat": "coat_orange",
        "skin": "skin",
    }
    return ScriptedChatModel.replying(
        calling(created("c1", "Evac drill", "wildfire-edge")),
        calling(tool_call("add_element", "c2", scenario_id="evac-drill", person=hiker)),
        calling(
            tool_call(
                "set_behaviour",
                "c3",
                scenario_id="evac-drill",
                target_id="hiker",
                tree_json=json.dumps(FLEE),
            )
        ),
        calling(
            tool_call(
                "set_behaviour",
                "c4",
                scenario_id="evac-drill",
                target_id="wind",
                tree_json=json.dumps(VEER),
            )
        ),
        calling(
            tool_call(
                "update_behaviour_node",
                "c5",
                scenario_id="evac-drill",
                target_id="hiker",
                node_id="run",
                node_json=json.dumps(SPRINT),
            )
        ),
        calling(tool_call("get_behaviour", "c6", scenario_id="evac-drill", target_id="hiker")),
        calling(created("c7", "Wildfire evacuation", "wildfire-evacuation")),
        answer("The hiker sprints from the fire; the wind veers to 300° after 20 s."),
    )


async def test_an_agent_turn_gives_a_hiker_and_the_wind_their_trees(tmp_path: Path) -> None:
    # Given the station with an agent scripted to run an evacuation drill
    async with a_station(tmp_path, an_agent_running_an_evacuation_drill()) as station:
        # When the agent takes its turn and the page asks for the scenario
        await asyncio.to_thread(station.turn, "Have a hiker flee the fire as the wind veers")
        status, body = await asyncio.to_thread(station.get, "/sim/assets/scenarios/evac-drill.json")

    # Then the served scenario is valid, the hiker sprints, and the wind veers
    assert status == 200
    manifest = json.loads(body)
    validate_manifest(manifest)
    assert behaviour_of(manifest, "hiker") == fleeing(run=SPRINT)
    assert behaviour_of(manifest, "wind") == VEER


async def test_the_served_evacuation_preset_is_the_golden_the_renderer_validates(
    tmp_path: Path,
) -> None:
    # Given the station after the agent created the evacuation scenario
    async with a_station(tmp_path, an_agent_running_an_evacuation_drill()) as station:
        await asyncio.to_thread(station.turn, "Have a hiker flee the fire as the wind veers")
        _, body = await asyncio.to_thread(
            station.get, "/sim/assets/scenarios/wildfire-evacuation.json"
        )

    # Then it is the committed golden the Rust renderer's tests parse
    assert json.loads(body) == json.loads(GOLDEN.read_text(encoding="utf-8"))
