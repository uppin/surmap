"""Acceptance: a model flies a simulated sortie through the agent server's fleet tools.

A scripted model drives real chat turns on the real agent server (`build_agent_description`
with a `SimulationRig`, on `HypercornHost` port 0). A fake simulation page is linked over the
real `/sim/fleet` WebSocket: it applies each command with a scripted seq and simulation time,
and reports telemetry when the test says. The model reads every tool's answer in its history.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from langchain_core.messages import ToolMessage

from surmap.agent.contracts import tool_contracts
from surmap.agent.proto import fleet_tools_pb2 as pb
from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call, tool_message_for
from tests.fleet_fakes import Applies, drone_frame
from tests.fleet_tool_fakes import SCENARIO, SW_D1, a_fleet_station

FLEET_TOOL_NAMES = [
    contract.name for contract in tool_contracts(pb.DESCRIPTOR.services_by_name["FleetTools"])
]
# What the page answers the sortie's three commands with.
THE_SORTIE_S_ANSWERS = (
    Applies(seq=1, at_s=2.0),
    Applies(seq=2, at_s=9.5),
    Applies(seq=3, at_s=12.5),
)


def an_agent_flying_a_sortie() -> ScriptedChatModel:
    """Turn 1: list the nests and launch nest-sw-d1. Turn 2, once it is airborne: a detour for
    a closer look, then its camera on screen."""
    return ScriptedChatModel.replying(
        calling(tool_call("list_nests", "c1", scenario_id=SCENARIO)),
        calling(
            tool_call(
                "launch_drone",
                "c2",
                scenario_id=SCENARIO,
                drone_id=SW_D1,
                route={
                    "waypoints": [
                        {"east": -20.0, "north": 0.0, "up": 15.0},
                        {"east": -20.0, "north": 60.0, "up": 18.0},
                    ],
                    "speed_m_s": 6.0,
                    "on_complete": "ROUTE_END_HOVER",
                },
            )
        ),
        answer("nest-sw-d1 is up."),
        calling(
            tool_call(
                "add_detour",
                "c3",
                scenario_id=SCENARIO,
                drone_id=SW_D1,
                waypoints=[{"east": 0.0, "north": 30.0, "up": 12.0}],
            )
        ),
        calling(tool_call("set_active_drone", "c4", scenario_id=SCENARIO, drone_id=SW_D1)),
        answer("nest-sw-d1 is taking a closer look; its camera is on screen."),
    )


def the_answer_to(model: ScriptedChatModel, call_id: str) -> dict[str, Any]:
    """The JSON a tool call answered with, as the model read it after the last turn."""
    message: ToolMessage = tool_message_for(model.histories[-1], call_id)
    assert message.status == "success", message.content
    body: dict[str, Any] = json.loads(str(message.content))
    return body


async def test_a_scripted_conversation_flies_a_sortie_through_the_agent_server(
    tmp_path: Path,
) -> None:
    # Given the station with a linked page, and an agent scripted to fly a sortie
    model = an_agent_flying_a_sortie()
    async with (
        a_fleet_station(tmp_path, model) as station,
        station.a_linked_page(*THE_SORTIE_S_ANSWERS) as sim,
    ):
        # When the agent launches nest-sw-d1, the page reports it cruising, and the agent then
        # sends it on a detour and puts its camera on screen
        await asyncio.to_thread(station.turn, "Fly nest-sw-d1 up the avenue")
        await station.reports(
            sim, 4.0, SW_D1, drone_frame(SW_D1, "cruising", (-20.0, 10.0, 15.0), targets_left=2)
        )
        await asyncio.to_thread(station.turn, "Take a closer look at the collapsed corner")

    # Then each tool answered, the page applied the three commands in order, and the agent read
    # the nests and the times each command took effect
    assert [command["type"] for command in sim.commands] == ["launch", "detour", "set_active"]
    assert [nest["id"] for nest in the_answer_to(model, "c1")["nests"]] == [
        "nest-sw",
        "nest-ne",
        "nest-roof",
    ]
    assert (
        the_answer_to(model, "c2"),
        the_answer_to(model, "c3"),
        the_answer_to(model, "c4"),
    ) == ({"seq": 1, "at_s": 2.0}, {"seq": 2, "at_s": 9.5}, {"seq": 3, "at_s": 12.5})


async def test_with_a_simulation_the_model_is_offered_the_fleet_tools(tmp_path: Path) -> None:
    # Given the station serving a simulation
    model = ScriptedChatModel.replying(answer("Ready."))
    async with a_fleet_station(tmp_path, model) as station:
        # When the user writes
        await asyncio.to_thread(station.turn, "hi")

    # Then the model was bound to every fleet tool
    assert set(FLEET_TOOL_NAMES) <= set(model.bound_tool_names[0])
