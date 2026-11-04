"""Acceptance: the station commands a running simulation's drones over `/sim/fleet`.

The real agent server (`build_agent_description` with a `SimulationRig`, on `HypercornHost` port
0) serves the earthquake-fleet scenario. A fake simulation page links with the `websockets`
client and speaks `fleet/v1` as plain JSON: it says hello, answers each command with a scripted
`applied` / `refused` (or not at all) and sends telemetry when told to. Commands go through the
scenario's `FleetController`, as the agent's tools will.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.server.app import AgentServerConfig, build_agent_description
from surmap.agent.server.sim_routes import SimulationRig
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.simulation.asset_sources import AmbientCg, PolyHaven, Sketchfab
from surmap.simulation.fleet.commands import (
    Detour,
    FleetCommand,
    Launch,
    Route,
    SetActive,
    Stamped,
)
from surmap.simulation.fleet.controller import (
    FleetController,
    FleetInvalid,
    FleetRefused,
    FleetTimeout,
    FleetTiming,
    FleetUnavailable,
    InvalidRule,
)
from surmap.simulation.fleet.link import CLOSE_ALREADY_LINKED, Applied, DroneTelemetry
from tests.agent_fakes import ScriptedChatModel, answer
from tests.agent_tool_fakes import a_tool_rig
from tests.fake_ollama import a_closed_ollama_url
from tests.fleet_fakes import (
    QUAKE_FLEET,
    THE_SHARED_LAUNCH,
    Answer,
    Applies,
    FakeSim,
    RecordingSleep,
    Refuses,
    StaysSilent,
    a_fleet_store,
    a_sim_page,
    drone_frame,
    eventually,
    telemetry_frame,
)
from tests.sim_fakes import POC_ASSETS, RecordingFetch

SCENARIO = QUAKE_FLEET
SW_D1 = "nest-sw-d1"
NE_D1 = "nest-ne-d1"
FIXTURES = Path(__file__).parent / "fixtures"


@dataclass(frozen=True)
class Station:
    """The agent server serving the earthquake-fleet scenario `quake-fleet`."""

    address: str
    rig: SimulationRig

    @property
    def controller(self) -> FleetController:
        return self.rig.fleet.controller(SCENARIO)

    @asynccontextmanager
    async def a_linked_page(self, *answers: Answer) -> AsyncIterator[FakeSim]:
        """A page that has linked the scenario and answers with `answers`."""
        async with a_sim_page(self.address, SCENARIO, answers) as sim:
            await eventually(lambda: self.controller.linked)
            yield sim


@asynccontextmanager
async def a_station(tmp_path: Path, timing: FleetTiming | None = None) -> AsyncIterator[Station]:
    fetch = RecordingFetch()
    simulation = SimulationRig(
        store=a_fleet_store(tmp_path),
        sources={
            "polyhaven": PolyHaven(fetch),
            "ambientcg": AmbientCg(fetch),
            "sketchfab": Sketchfab(fetch, token="t"),
        },
        static_assets=POC_ASSETS,
        fleet_timing=timing if timing is not None else FleetTiming(),
    )
    model = ScriptedChatModel.replying(answer("idle"))
    with a_tool_rig(tmp_path) as rig:
        config = AgentServerConfig(
            port=0, model_id="ollama:scripted", model_factory=lambda _: model
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
            yield Station(address=f"127.0.0.1:{ports.public}", rig=simulation)
        finally:
            await host.stop()


def the_shared_launch_json() -> dict[str, object]:
    shared: list[dict[str, object]] = json.loads(
        (FIXTURES / "fleet" / "commands.json").read_text(encoding="utf-8")
    )
    return shared[0]


async def test_a_linked_simulation_applies_a_launch_and_the_scenario_logs_it(
    tmp_path: Path,
) -> None:
    # Given a linked page that applies the next command as entry 1 at 41.25 s
    async with a_station(tmp_path) as station, station.a_linked_page(Applies(1, 41.25)) as sim:
        # When the station launches nest-sw-d1
        applied = await station.controller.send(THE_SHARED_LAUNCH)

    # Then the page got the shared launch, the station returns the page's stamp, and the
    # scenario's stored log holds the launch at that time
    assert sim.commands == [the_shared_launch_json()]
    assert applied == Applied(request=1, seq=1, at_s=41.25)
    session = station.rig.fleet.log_store.sessions(SCENARIO)[0].session_id
    assert station.rig.fleet.log_store.entries(session) == (Stamped(1, 41.25, THE_SHARED_LAUNCH),)


async def test_a_command_the_simulation_refuses_returns_its_reason_and_is_not_logged(
    tmp_path: Path,
) -> None:
    # Given a linked page that refuses the next command
    reason = "nest-sw-d1 is climbing: launch needs a docked drone"
    async with a_station(tmp_path) as station, station.a_linked_page(Refuses(3.5, reason)):
        # When the station launches nest-sw-d1, then the page's reason comes back
        with pytest.raises(FleetRefused, match=reason):
            await station.controller.send(THE_SHARED_LAUNCH)

    # And nothing is logged as applied
    assert station.controller.session_log() == ()


INVALID: dict[str, tuple[FleetCommand, InvalidRule]] = {
    "unknown drone": (SetActive("nest-zz-d9"), InvalidRule.UNKNOWN_DRONE),
    "empty route": (Launch(SW_D1, Route(())), InvalidRule.NO_WAYPOINTS),
    "speed": (
        Launch(SW_D1, Route(((0.0, 0.0, 15.0),), speed_m_s=12.0)),
        InvalidRule.SPEED_OUT_OF_RANGE,
    ),
    "altitude": (Launch(SW_D1, Route(((0.0, 0.0, 80.0),))), InvalidRule.HEIGHT_OUT_OF_RANGE),
    "bounds": (Launch(SW_D1, Route(((0.0, 650.0, 15.0),))), InvalidRule.OUT_OF_BOUNDS),
    "phase": (Detour(SW_D1, ((0.0, 35.0, 18.0),)), InvalidRule.NOT_FLYING),
}


@pytest.mark.parametrize(("command", "rule"), INVALID.values(), ids=INVALID.keys())
async def test_an_invalid_command_is_refused_without_reaching_the_simulation(
    tmp_path: Path, command: FleetCommand, rule: InvalidRule
) -> None:
    # Given a linked page whose drones are all on their pads
    async with a_station(tmp_path) as station, station.a_linked_page() as sim:
        # When the station sends an invalid command, then it names the broken rule
        with pytest.raises(FleetInvalid) as refused:
            await station.controller.send(command)
        # And a valid command sent after it is the only one the page ever receives
        await station.controller.send(SetActive(NE_D1))

    assert refused.value.rule is rule
    assert sim.commands == [{"type": "set_active", "drone": NE_D1}]


async def test_without_a_linked_page_a_command_reports_no_simulation_connected(
    tmp_path: Path,
) -> None:
    # Given the station with no page linked
    async with a_station(tmp_path) as station:
        # When it launches a drone, then it reports that no simulation is connected
        with pytest.raises(
            FleetUnavailable, match="no simulation connected for scenario quake-fleet"
        ):
            await station.controller.send(THE_SHARED_LAUNCH)


async def test_after_the_page_closes_a_command_reports_no_simulation_connected(
    tmp_path: Path,
) -> None:
    # Given a page that linked and then closed
    async with a_station(tmp_path) as station:
        async with station.a_linked_page():
            pass
        await eventually(lambda: not station.controller.linked)

        # When the station launches a drone, then no simulation is connected
        with pytest.raises(FleetUnavailable):
            await station.controller.send(THE_SHARED_LAUNCH)


async def test_a_silent_page_times_out_after_five_seconds(tmp_path: Path) -> None:
    # Given a linked page that never answers, and a station clock that remembers every wait
    sleep = RecordingSleep()
    async with (
        a_station(tmp_path, FleetTiming(sleep=sleep)) as station,
        station.a_linked_page(StaysSilent()) as sim,
    ):
        # When the station launches a drone, then it times out
        with pytest.raises(FleetTimeout):
            await station.controller.send(THE_SHARED_LAUNCH)
        await eventually(lambda: len(sim.commands) == 1)

    # And the launch reached the page, and the station waited five seconds for its answer
    assert (sim.commands, sleep.waits) == ([the_shared_launch_json()], [5.0])


async def test_telemetry_is_what_the_controller_reports(tmp_path: Path) -> None:
    # Given a linked page
    async with a_station(tmp_path) as station, station.a_linked_page() as sim:
        # When it reports nest-sw-d1 cruising and active, and nest-ne-d1 docked
        await sim.send_telemetry(
            telemetry_frame(
                41.5,
                SW_D1,
                [
                    drone_frame(
                        SW_D1,
                        "cruising",
                        (-20.0, 12.5, 15.0),
                        yaw_deg=90.0,
                        speed_m_s=6.0,
                        targets_left=2,
                    ),
                    drone_frame(NE_D1, "docked", (40.0, 100.0, 0.0), yaw_deg=225.0),
                ],
            )
        )
        await eventually(lambda: station.controller.drones() != ())

        # Then the controller reports each drone's phase and pose, and the active drone
        assert station.controller.drones() == (
            DroneTelemetry(SW_D1, "cruising", (-20.0, 12.5, 15.0), 90.0, 6.0, 2),
            DroneTelemetry(NE_D1, "docked", (40.0, 100.0, 0.0), 225.0, 0.0, 0),
        )
        assert station.controller.active() == SW_D1


async def test_a_second_page_for_the_same_scenario_is_refused(tmp_path: Path) -> None:
    # Given a linked page
    async with a_station(tmp_path) as station, station.a_linked_page() as first:
        # When a second page links the same scenario
        async with a_sim_page(station.address, SCENARIO) as second:
            refused_with = await second.close_code()

        # Then the second is closed as already linked, and the first still answers
        applied = await station.controller.send(SetActive(NE_D1))

    assert refused_with == CLOSE_ALREADY_LINKED
    assert (first.commands, applied.request) == ([{"type": "set_active", "drone": NE_D1}], 1)


async def test_the_stored_log_exports_as_a_fleet_log_file(tmp_path: Path) -> None:
    # Given a linked page that applies a launch as entry 1, refuses the next command (taking
    # seq 2 in its own log) and applies a set_active as entry 3
    async with (
        a_station(tmp_path) as station,
        station.a_linked_page(
            Applies(1, 2.0),
            Refuses(5.0, "nest-ne-d1 is landing: launch needs a docked drone"),
            Applies(3, 12.5),
        ),
    ):
        # When the station sends the three commands
        await station.controller.send(THE_SHARED_LAUNCH)
        with pytest.raises(FleetRefused):
            await station.controller.send(Launch(NE_D1, Route(((30.0, 90.0, 15.0),))))
        await station.controller.send(SetActive(SW_D1))

    # Then the session exports as the `--fleet-log` file the renderer reads, line for line
    session = station.rig.fleet.log_store.sessions(SCENARIO)[0].session_id
    assert station.rig.fleet.log_store.export_jsonl(session) == (
        FIXTURES / "fleet_link" / "session.fleet.jsonl"
    ).read_text(encoding="utf-8")
