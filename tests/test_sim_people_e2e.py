"""Acceptance: the agent places survivors in the poses a survey finds them, and the station serves
them. Same harness as tests/test_sim_behaviour_e2e.py."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from surmap.simulation.scenario_manifest import validate_manifest
from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call
from tests.sim_fakes import people_of
from tests.test_sim_behaviour_e2e import created
from tests.test_sim_scenario_e2e import a_station

GOLDEN = Path(__file__).parent / "fixtures" / "sim_scenario" / "earthquake-survivors.json"


def an_agent_placing_survivors() -> ScriptedChatModel:
    def survivor(person_id: str, north: float, pose: str) -> dict[str, object]:
        return {
            "id": person_id,
            "position": {"east": -15.0, "north": north, "up": 0.0},
            "coat": "coat_yellow",
            "pose": pose,
            "height_m": 1.7,
        }

    return ScriptedChatModel.replying(
        calling(created("c1", "Survivors", "earthquake-block")),
        calling(
            tool_call(
                "add_element", "c2", scenario_id="survivors", person=survivor("s1", 31.0, "lying")
            )
        ),
        calling(
            tool_call(
                "add_element", "c3", scenario_id="survivors", person=survivor("s2", 34.0, "waving")
            )
        ),
        calling(created("c4", "Earthquake survivors", "earthquake-survivors")),
        answer("One survivor lies by the rubble, one waves for help."),
    )


async def test_an_agent_turn_places_a_lying_and_a_waving_survivor(tmp_path: Path) -> None:
    # Given the station with an agent scripted to place survivors
    async with a_station(tmp_path, an_agent_placing_survivors()) as station:
        # When the agent takes its turn and the page asks for the scenario
        await asyncio.to_thread(station.turn, "Place a lying and a waving survivor by the rubble")
        status, body = await asyncio.to_thread(station.get, "/sim/assets/scenarios/survivors.json")

    # Then the served scenario is valid and holds both survivors in their poses
    assert status == 200
    manifest = json.loads(body)
    validate_manifest(manifest)
    poses = {str(p["id"]): p.get("pose") for p in people_of(manifest)}
    assert (poses["s1"], poses["s2"]) == ("lying", "waving")


async def test_the_served_survivors_preset_is_the_golden_the_renderer_validates(
    tmp_path: Path,
) -> None:
    # Given the station after the agent created the survivors scenario
    async with a_station(tmp_path, an_agent_placing_survivors()) as station:
        await asyncio.to_thread(station.turn, "Place a lying and a waving survivor by the rubble")
        _, body = await asyncio.to_thread(
            station.get, "/sim/assets/scenarios/earthquake-survivors.json"
        )

    # Then it is the committed golden the Rust renderer's tests parse
    assert json.loads(body) == json.loads(GOLDEN.read_text(encoding="utf-8"))
