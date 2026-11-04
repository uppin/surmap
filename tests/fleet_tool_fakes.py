"""The station the fleet tools are tested on: the real agent server with a `SimulationRig` over the
earthquake-fleet scenario `quake-fleet`, on `HypercornHost` port 0, so a fake simulation page
(`tests.fleet_fakes`) links over the real `/sim/fleet` WebSocket.

The tools are called two ways: in process, through `fleet_tool_handlers` over the same rig the
server links (`FleetStation.call`), and as a model would, through a chat turn on the server
(`FleetStation.turn`).
"""

from __future__ import annotations

import http.client
import struct
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.proto import chat_pb2
from surmap.agent.proto import fleet_tools_pb2 as pb
from surmap.agent.proto import simulation_tools_pb2 as sim_pb
from surmap.agent.server.app import AgentServerConfig, build_agent_description
from surmap.agent.server.sim_routes import SimulationRig
from surmap.agent.services import Handler
from surmap.agent.tools.fleet_handlers import fleet_tool_handlers
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.simulation.asset_sources import AmbientCg, PolyHaven, Sketchfab
from surmap.simulation.fleet.controller import FleetController, FleetTiming
from surmap.simulation.scenario_manifest import load_presets
from surmap.simulation.scenario_store import ScenarioStore
from tests.agent_fakes import ScriptedChatModel, answer
from tests.agent_server_fakes import STEP_TIMEOUT_S
from tests.agent_tool_fakes import a_tool_rig
from tests.fake_ollama import a_closed_ollama_url
from tests.fleet_fakes import (
    Answer,
    FakeSim,
    Frame,
    a_sim_page,
    eventually,
    telemetry_frame,
)
from tests.sim_fakes import POC_ASSETS, RecordingFetch

SCENARIO = "quake-fleet"
SW_D1 = "nest-sw-d1"
SW_D2 = "nest-sw-d2"
NE_D1 = "nest-ne-d1"
STREAM_TURN = "/surmap.agent.v1.ChatService/StreamTurn"
FIXTURES = Path(__file__).parent / "fixtures"

# The pads of the earthquake-fleet preset: id, ENU centre, heading, drones.
PADS: tuple[tuple[str, tuple[float, float, float], float, tuple[str, ...]], ...] = (
    ("nest-sw", (-40.0, -20.0, 0.0), 45.0, ("nest-sw-d1", "nest-sw-d2")),
    ("nest-ne", (40.0, 100.0, 0.0), 225.0, ("nest-ne-d1", "nest-ne-d2")),
    ("nest-roof", (78.55, 22.0, 16.5), 180.0, ("nest-roof-d1",)),
)


def enu(east: float, north: float, up: float) -> sim_pb.EnuPoint:
    return sim_pb.EnuPoint(east=east, north=north, up=up)


def a_route(
    *waypoints: tuple[float, float, float],
    speed_m_s: float | None = None,
    on_complete: pb.RouteEnd = pb.ROUTE_END_UNSPECIFIED,
) -> pb.FlightRoute:
    route = pb.FlightRoute(waypoints=[enu(*w) for w in waypoints], on_complete=on_complete)
    if speed_m_s is not None:
        route.speed_m_s = speed_m_s
    return route


# The first command of `tests/fixtures/fleet/commands.json`, as the agent asks for it.
THE_SHARED_ROUTE = a_route(
    (-20.0, 0.0, 15.0), (-20.0, 60.0, 18.0), speed_m_s=6.0, on_complete=pb.ROUTE_END_HOVER
)


def position_of(status: pb.DroneStatus) -> tuple[float, float, float]:
    return (status.position.east, status.position.north, status.position.up)


@dataclass
class FleetStation:
    """The agent server serving `quake-fleet`, and the fleet tools over its rig."""

    address: str
    rig: SimulationRig
    model: ScriptedChatModel
    tools: Mapping[str, Handler] = field(default_factory=dict)

    @property
    def controller(self) -> FleetController:
        return self.rig.fleet.controller(SCENARIO)

    async def call(self, rpc: str, request: object) -> object:
        """Runs one fleet tool in process, as the server binds it."""
        return await self.tools[rpc](request, None)

    @asynccontextmanager
    async def a_linked_page(self, *answers: Answer) -> AsyncIterator[FakeSim]:
        """A page that has linked the scenario and answers with `answers`."""
        async with a_sim_page(self.address, SCENARIO, answers) as sim:
            await eventually(lambda: self.controller.linked)
            yield sim

    async def reports(
        self, sim: FakeSim, sim_t_s: float, active: str | None, *drones: Frame
    ) -> None:
        """The page sends telemetry, and the station has it."""
        await sim.send_telemetry(telemetry_frame(sim_t_s, active, drones))
        expected = {(d["id"], d["phase"]) for d in drones}
        await eventually(
            lambda: (
                expected <= {(d.id, d.phase) for d in self.controller.drones()}
                and self.controller.active() == active
            )
        )

    def turn(self, text: str, conversation_id: str = "fleet-1") -> None:
        """One chat turn on the server (blocking: run it in a thread)."""
        payload = chat_pb2.StreamTurnRequest(
            conversation_id=conversation_id, text=text
        ).SerializeToString()
        connection = http.client.HTTPConnection(self.address, timeout=STEP_TIMEOUT_S * 4)
        try:
            connection.request(
                "POST",
                STREAM_TURN,
                body=struct.pack(">BI", 0, len(payload)) + payload,
                headers={"content-type": "application/connect+proto"},
            )
            assert connection.getresponse().read()
        finally:
            connection.close()


@asynccontextmanager
async def a_fleet_station(
    tmp_path: Path,
    model: ScriptedChatModel | None = None,
    timing: FleetTiming | None = None,
) -> AsyncIterator[FleetStation]:
    """The station with the earthquake-fleet scenario `quake-fleet` created."""
    store = ScenarioStore(
        db_path=tmp_path / "simulation.sqlite",
        library_dir=tmp_path / "library",
        presets=load_presets(POC_ASSETS),
    )
    store.create_scenario("Quake fleet", "earthquake-fleet")
    fetch = RecordingFetch()
    simulation = SimulationRig(
        store=store,
        sources={
            "polyhaven": PolyHaven(fetch),
            "ambientcg": AmbientCg(fetch),
            "sketchfab": Sketchfab(fetch, token="t"),
        },
        static_assets=POC_ASSETS,
        fleet_timing=timing if timing is not None else FleetTiming(),
    )
    chat_model = model if model is not None else ScriptedChatModel.replying(answer("idle"))
    with a_tool_rig(tmp_path) as rig:
        config = AgentServerConfig(
            port=0, model_id="ollama:scripted", model_factory=lambda _: chat_model
        )
        description = build_agent_description(
            config,
            workspace=rig.workspace,
            geometry=rig.workspace.geometry,
            registry=ChatModelRegistry(environ={"SURMAP_OLLAMA_URL": a_closed_ollama_url()}),
            simulation=simulation,
        )
        host = HypercornHost(description, None, host="127.0.0.1", port=0)
        ports = await host.start()
        try:
            yield FleetStation(
                address=f"127.0.0.1:{ports.public}",
                rig=simulation,
                model=chat_model,
                tools=fleet_tool_handlers(simulation.store, simulation.fleet),
            )
        finally:
            await host.stop()
