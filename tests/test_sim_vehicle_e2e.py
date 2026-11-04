"""Acceptance: the agent puts vehicles that drive into a scenario, and the station serves them.

Same harness as tests/test_sim_behaviour_e2e.py: a scripted model drives a real agent turn on a
real socket over a real SQLite store; the page's request for the scenario is then made.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from surmap.simulation.scenario_manifest import behaviour_of, validate_manifest
from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call
from tests.sim_fakes import vehicles_of
from tests.test_sim_behaviour_e2e import created
from tests.test_sim_scenario_e2e import a_station

GOLDEN = Path(__file__).parent / "fixtures" / "sim_scenario" / "street-traffic.json"

UP_THE_AVENUE: dict[str, object] = {
    "node": "follow_path",
    "enu": [[2.5, 120.0]],
    "speed_m_s": 10.0,
}


def an_agent_staging_an_ambulance_run() -> ScriptedChatModel:
    ambulance = {
        "id": "ambulance-1",
        "vehicle_class": "truck",
        "position": {"east": 2.5, "north": -20.0, "up": 0.0},
        "yaw_deg": 90.0,
        "behaviour_json": json.dumps(UP_THE_AVENUE),
    }
    return ScriptedChatModel.replying(
        calling(created("c1", "Ambulance run", "earthquake-block")),
        calling(tool_call("add_element", "c2", scenario_id="ambulance-run", vehicle=ambulance)),
        calling(created("c3", "Street traffic", "street-traffic")),
        answer("A truck drives up the avenue; the street-traffic scenario is ready."),
    )


async def test_an_agent_turn_adds_a_truck_that_drives_up_the_avenue(tmp_path: Path) -> None:
    # Given the station with an agent scripted to stage an ambulance run
    async with a_station(tmp_path, an_agent_staging_an_ambulance_run()) as station:
        # When the agent takes its turn and the page asks for the scenario
        await asyncio.to_thread(station.turn, "Send a truck up the avenue")
        status, body = await asyncio.to_thread(
            station.get, "/sim/assets/scenarios/ambulance-run.json"
        )

    # Then the served scenario is valid and holds the truck with its drive
    assert status == 200
    manifest = json.loads(body)
    validate_manifest(manifest)
    trucks = vehicles_of(manifest)
    assert [(t["id"], t["class"], t["yaw_deg"]) for t in trucks] == [("ambulance-1", "truck", 90.0)]
    assert behaviour_of(manifest, "ambulance-1") == UP_THE_AVENUE


async def test_the_served_street_traffic_preset_is_the_golden_the_renderer_validates(
    tmp_path: Path,
) -> None:
    # Given the station after the agent created the street-traffic scenario
    async with a_station(tmp_path, an_agent_staging_an_ambulance_run()) as station:
        await asyncio.to_thread(station.turn, "Send a truck up the avenue")
        _, body = await asyncio.to_thread(station.get, "/sim/assets/scenarios/street-traffic.json")

    # Then it is the committed golden the Rust renderer's tests parse
    assert json.loads(body) == json.loads(GOLDEN.read_text(encoding="utf-8"))
