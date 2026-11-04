"""Acceptance: the agent floods a street and launches a rescue boat on it, and the station serves
it. Same harness as tests/test_sim_behaviour_e2e.py."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from surmap.simulation.scenario_manifest import behaviour_of, validate_manifest
from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call
from tests.sim_fakes import vehicles_of
from tests.test_sim_behaviour_e2e import created
from tests.test_sim_scenario_e2e import a_station

GOLDEN = Path(__file__).parent / "fixtures" / "sim_scenario" / "flood-rescue.json"

SHUTTLE: dict[str, object] = {
    "node": "repeat",
    "child": {"node": "follow_path", "enu": [[0.0, 90.0], [0.0, 10.0]], "speed_m_s": 4.0},
}


def an_agent_launching_a_rescue_boat() -> ScriptedChatModel:
    floodwater = {
        "id": "floodwater",
        "material": "water",
        "size": {"east": 10.0, "north": 100.0, "up": 0.6},
        "position": {"east": 0.0, "north": 50.0, "up": 0.0},
        "water": True,
    }
    boat = {
        "id": "rescue-1",
        "vehicle_class": "boat",
        "position": {"east": 0.0, "north": 10.0, "up": 0.0},
        "behaviour_json": json.dumps(SHUTTLE),
    }
    return ScriptedChatModel.replying(
        calling(created("c1", "Flood drill", "flood-street")),
        calling(tool_call("add_element", "c2", scenario_id="flood-drill", box=floodwater)),
        calling(tool_call("add_element", "c3", scenario_id="flood-drill", vehicle=boat)),
        calling(created("c4", "Flood rescue", "flood-rescue")),
        answer("The avenue is flooded; a rescue boat shuttles along it."),
    )


async def test_an_agent_turn_floods_the_avenue_and_launches_a_rescue_boat(tmp_path: Path) -> None:
    # Given the station with an agent scripted to run a flood drill
    async with a_station(tmp_path, an_agent_launching_a_rescue_boat()) as station:
        # When the agent takes its turn and the page asks for the scenario
        await asyncio.to_thread(station.turn, "Flood the avenue and launch a rescue boat")
        status, body = await asyncio.to_thread(
            station.get, "/sim/assets/scenarios/flood-drill.json"
        )

    # Then the served scenario is valid, the street is water, and the boat shuttles on it
    assert status == 200
    manifest = json.loads(body)
    validate_manifest(manifest)
    water = [e for e in manifest["elements"] if e["id"] == "floodwater"]
    assert water[0]["water"] is True
    assert [v["class"] for v in vehicles_of(manifest)] == ["boat"]
    assert behaviour_of(manifest, "rescue-1") == SHUTTLE


async def test_the_served_flood_rescue_preset_is_the_golden_the_renderer_validates(
    tmp_path: Path,
) -> None:
    # Given the station after the agent created the flood-rescue scenario
    async with a_station(tmp_path, an_agent_launching_a_rescue_boat()) as station:
        await asyncio.to_thread(station.turn, "Flood the avenue and launch a rescue boat")
        _, body = await asyncio.to_thread(station.get, "/sim/assets/scenarios/flood-rescue.json")

    # Then it is the committed golden the Rust renderer's tests parse
    assert json.loads(body) == json.loads(GOLDEN.read_text(encoding="utf-8"))
