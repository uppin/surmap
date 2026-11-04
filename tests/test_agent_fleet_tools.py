"""The fleet tools: the survey agent tasks the running simulation's drones.

Handler tests over the real agent server's `SimulationRig` (`tests.fleet_tool_fakes`): a proto
request in, a proto response or a `ConnectError` out, with a fake simulation page linked over
the real `/sim/fleet` WebSocket (`tests.fleet_fakes`). Below them, the handlers' own pure parts:
the error mapping, request → command conversion and the drone and nest reports.
"""

from __future__ import annotations

import asyncio
import http.client
import json
from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from google.protobuf.json_format import MessageToDict

from surmap.agent.contracts import (
    ExecutionMode,
    ExecutionPolicy,
    OnTimeout,
    tool_contracts,
)
from surmap.agent.proto import fleet_tools_pb2 as pb
from surmap.agent.tools.fleet_handlers import (
    CommandRequest,
    drone_map_counts,
    drone_map_status_handler,
    drone_phase,
    drone_statuses,
    fleet_command,
    fleet_error,
    fleet_nest,
    flight_route,
)
from surmap.simulation.fleet.commands import (
    Detour,
    FleetCommand,
    Launch,
    Recall,
    Route,
    SetActive,
    SetRoute,
)
from surmap.simulation.fleet.controller import (
    FleetError,
    FleetInvalid,
    FleetRefused,
    FleetTimeout,
    FleetTiming,
    FleetUnavailable,
    InvalidRule,
)
from surmap.simulation.fleet.link import DroneTelemetry, Phase
from surmap.simulation.fleet.perception import DroneCounts
from surmap.simulation.fleet_nests import Nest
from tests.fleet_fakes import (
    Applies,
    RecordingSleep,
    Refuses,
    StaysSilent,
    drone_frame,
    eventually,
)
from tests.fleet_perception_fakes import PerceptionRig, a_perception, blocks
from tests.fleet_tool_fakes import (
    FIXTURES,
    NE_D1,
    PADS,
    SCENARIO,
    SW_D1,
    THE_SHARED_ROUTE,
    FleetStation,
    a_fleet_station,
    a_route,
    enu,
    position_of,
)

FLEET_TOOLS = pb.DESCRIPTOR.services_by_name["FleetTools"]
SW_PAD = (-40.0, -20.0, 0.0)


# ---- requests ---------------------------------------------------------------------------------


def a_launch(drone: str = SW_D1, route: pb.FlightRoute = THE_SHARED_ROUTE) -> pb.LaunchDroneRequest:
    return pb.LaunchDroneRequest(scenario_id=SCENARIO, drone_id=drone, route=route)


def a_new_route(drone: str, route: pb.FlightRoute) -> pb.SetRouteRequest:
    return pb.SetRouteRequest(scenario_id=SCENARIO, drone_id=drone, route=route)


def a_detour(drone: str, *waypoints: tuple[float, float, float]) -> pb.AddDetourRequest:
    return pb.AddDetourRequest(
        scenario_id=SCENARIO, drone_id=drone, waypoints=[enu(*w) for w in waypoints]
    )


def a_recall(drone: str) -> pb.RecallDroneRequest:
    return pb.RecallDroneRequest(scenario_id=SCENARIO, drone_id=drone)


def making_active(drone: str) -> pb.SetActiveDroneRequest:
    return pb.SetActiveDroneRequest(scenario_id=SCENARIO, drone_id=drone)


def the_drones(scenario: str = SCENARIO) -> pb.ListDronesRequest:
    return pb.ListDronesRequest(scenario_id=scenario)


# ---- reading answers --------------------------------------------------------------------------


async def the_report(station: FleetStation) -> pb.ListDronesResponse:
    report = await station.call("ListDrones", the_drones())
    assert isinstance(report, pb.ListDronesResponse)
    return report


def simulation_time_in(report: pb.ListDronesResponse) -> object:
    """The report's `sim_t_s` as it goes over the wire; `None` when it is not set."""
    return MessageToDict(report, preserving_proto_field_name=True).get("sim_t_s")


def phases_in(report: pb.ListDronesResponse) -> dict[str, pb.DronePhase]:
    return {drone.id: drone.phase for drone in report.drones}


def acknowledged(result: object) -> tuple[int, float]:
    assert isinstance(result, pb.FleetCommandResult)
    return (result.seq, result.at_s)


async def refusal_of(station: FleetStation, rpc: str, request: object) -> ConnectError:
    with pytest.raises(ConnectError) as raised:
        await station.call(rpc, request)
    return raised.value


def the_shared_launch_json() -> dict[str, object]:
    shared: list[dict[str, object]] = json.loads(
        (FIXTURES / "fleet" / "commands.json").read_text(encoding="utf-8")
    )
    return shared[0]


def cruising(drone: str = SW_D1) -> dict[str, object]:
    return drone_frame(drone, "cruising", (-20.0, 10.0, 15.0), speed_m_s=6.0, targets_left=2)


# ---- acceptance: the tools against a linked page ----------------------------------------------


async def test_the_agent_launches_a_drone_and_hears_when_it_took_off(tmp_path: Path) -> None:
    # Given a linked page that applies the next command as entry 1 at 2.0 s
    async with (
        a_fleet_station(tmp_path) as station,
        station.a_linked_page(Applies(seq=1, at_s=2.0)) as sim,
    ):
        # When the agent launches nest-sw-d1 on a route, and the page reports it climbing
        result = await station.call("LaunchDrone", a_launch(SW_D1, THE_SHARED_ROUTE))
        await station.reports(sim, 2.5, SW_D1, drone_frame(SW_D1, "climbing", (-40.0, -20.0, 3.0)))
        report = await the_report(station)

    # Then the launch is acknowledged with its time, reached the page as the shared launch,
    # and the drone is reported climbing
    assert acknowledged(result) == (1, 2.0)
    assert sim.commands == [the_shared_launch_json()]
    assert phases_in(report)[SW_D1] == pb.DRONE_PHASE_CLIMBING


async def test_a_new_route_and_a_detour_reach_an_airborne_drone(tmp_path: Path) -> None:
    # Given nest-sw-d1 launched and reported cruising
    async with a_fleet_station(tmp_path) as station, station.a_linked_page() as sim:
        await station.call("LaunchDrone", a_launch())
        await station.reports(sim, 4.0, SW_D1, cruising())

        # When the agent gives it a new route, then a detour
        rerouted = await station.call(
            "SetRoute", a_new_route(SW_D1, a_route((10.0, 40.0, 20.0), speed_m_s=4.0))
        )
        detoured = await station.call("AddDetour", a_detour(SW_D1, (0.0, 30.0, 12.0)))

    # Then both are applied, in order, as the commands the page received
    assert (acknowledged(rerouted), acknowledged(detoured)) == ((2, 2.0), (3, 3.0))
    assert sim.commands[1:] == [
        {
            "type": "set_route",
            "drone": SW_D1,
            "route": {"waypoints": [[10.0, 40.0, 20.0]], "speed_m_s": 4.0},
        },
        {"type": "detour", "drone": SW_D1, "waypoints": [[0.0, 30.0, 12.0]]},
    ]


async def test_a_detour_for_a_docked_drone_fails_naming_its_phase(tmp_path: Path) -> None:
    # Given a linked page and nest-sw-d1 still on its pad
    async with a_fleet_station(tmp_path) as station, station.a_linked_page() as sim:
        # When the agent sends it on a detour
        refused = await refusal_of(station, "AddDetour", a_detour(SW_D1, (0.0, 30.0, 12.0)))

    # Then the station refuses it as a drone not in flight, naming the phase, and sends nothing
    assert refused.code == Code.INVALID_ARGUMENT
    assert refused.message.startswith("not_flying")
    assert "docked" in refused.message
    assert sim.commands == []


async def test_a_recalled_drone_is_reported_docked(tmp_path: Path) -> None:
    # Given nest-sw-d1 launched and reported cruising
    async with a_fleet_station(tmp_path) as station, station.a_linked_page() as sim:
        await station.call("LaunchDrone", a_launch())
        await station.reports(sim, 4.0, SW_D1, cruising())

        # When the agent recalls it, and the page later reports it back on its pad
        recalled = await station.call("RecallDrone", a_recall(SW_D1))
        await station.reports(sim, 30.0, SW_D1, drone_frame(SW_D1, "docked", SW_PAD))
        report = await the_report(station)

    # Then the recall is applied and the drone is reported docked
    assert acknowledged(recalled) == (2, 2.0)
    assert sim.commands[-1] == {"type": "recall", "drone": SW_D1}
    assert phases_in(report)[SW_D1] == pb.DRONE_PHASE_DOCKED


async def test_set_active_drone_changes_the_active_drone(tmp_path: Path) -> None:
    # Given a linked page showing nest-sw-d1's eyes
    async with (
        a_fleet_station(tmp_path) as station,
        station.a_linked_page(Applies(seq=1, at_s=12.5)) as sim,
    ):
        await station.reports(sim, 12.0, SW_D1, drone_frame(SW_D1, "docked", SW_PAD))

        # When the agent makes nest-ne-d1 active, and the page reports the switch
        result = await station.call("SetActiveDrone", making_active(NE_D1))
        await station.reports(sim, 12.6, NE_D1, drone_frame(SW_D1, "docked", SW_PAD))
        report = await the_report(station)

    # Then the switch is acknowledged and nest-ne-d1 is the active drone
    assert acknowledged(result) == (1, 12.5)
    assert sim.commands == [{"type": "set_active", "drone": NE_D1}]
    assert report.active == NE_D1


async def test_list_drones_reports_the_pages_simulation_time(tmp_path: Path) -> None:
    # Given a linked page whose last telemetry is stamped 41.5 s
    async with a_fleet_station(tmp_path) as station:
        async with station.a_linked_page() as sim:
            await station.reports(sim, 41.5, SW_D1, cruising())

            # When the agent lists the drones while the page is linked, and again once it is gone
            linked = await the_report(station)
        await eventually(lambda: not station.controller.linked)
        unlinked = await the_report(station)

    # Then the linked report carries the page's simulation time, and the unlinked one none
    assert (simulation_time_in(linked), simulation_time_in(unlinked)) == (41.5, None)


UNLINKED_COMMANDS: dict[str, tuple[str, CommandRequest]] = {
    "launch": ("LaunchDrone", a_launch()),
    "set active": ("SetActiveDrone", making_active(NE_D1)),
}


@pytest.mark.parametrize(
    ("rpc", "request_"), UNLINKED_COMMANDS.values(), ids=UNLINKED_COMMANDS.keys()
)
async def test_without_a_linked_page_commands_fail_unavailable(
    tmp_path: Path, rpc: str, request_: CommandRequest
) -> None:
    # Given the station with no simulation page linked
    async with a_fleet_station(tmp_path) as station:
        # When the agent sends a command a docked drone accepts
        refused = await refusal_of(station, rpc, request_)

    # Then it fails as unavailable: no simulation connected
    assert refused.code == Code.UNAVAILABLE
    assert "no simulation connected" in refused.message


async def test_without_a_linked_page_drones_report_unlinked_and_docked_at_their_pads(
    tmp_path: Path,
) -> None:
    # Given the station with no simulation page linked
    async with a_fleet_station(tmp_path) as station:
        # When the agent lists the drones
        report = await the_report(station)

    # Then the report is unlinked, with every drone docked on its nest's pad
    assert report.linked is False
    assert [(d.id, d.nest, d.phase, position_of(d)) for d in report.drones] == [
        ("nest-sw-d1", "nest-sw", pb.DRONE_PHASE_DOCKED, (-40.0, -20.0, 0.0)),
        ("nest-sw-d2", "nest-sw", pb.DRONE_PHASE_DOCKED, (-40.0, -20.0, 0.0)),
        ("nest-ne-d1", "nest-ne", pb.DRONE_PHASE_DOCKED, (40.0, 100.0, 0.0)),
        ("nest-ne-d2", "nest-ne", pb.DRONE_PHASE_DOCKED, (40.0, 100.0, 0.0)),
        ("nest-roof-d1", "nest-roof", pb.DRONE_PHASE_DOCKED, (78.55, 22.0, 16.5)),
    ]


INVALID_ROUTES: dict[str, tuple[pb.FlightRoute, InvalidRule]] = {
    "empty": (a_route(), InvalidRule.NO_WAYPOINTS),
    "too high": (a_route((-20.0, 0.0, 80.0)), InvalidRule.HEIGHT_OUT_OF_RANGE),
    "too fast": (a_route((-20.0, 0.0, 15.0), speed_m_s=12.0), InvalidRule.SPEED_OUT_OF_RANGE),
    "off the scene": (a_route((900.0, 0.0, 15.0)), InvalidRule.OUT_OF_BOUNDS),
}


@pytest.mark.parametrize(("route", "rule"), INVALID_ROUTES.values(), ids=INVALID_ROUTES.keys())
async def test_an_invalid_route_is_refused_with_the_rule(
    tmp_path: Path, route: pb.FlightRoute, rule: InvalidRule
) -> None:
    # Given a linked page
    async with a_fleet_station(tmp_path) as station, station.a_linked_page() as sim:
        # When the agent launches nest-sw-d1 on a route that breaks a rule
        refused = await refusal_of(station, "LaunchDrone", a_launch(SW_D1, route))

    # Then the station refuses it as an invalid argument led by the rule, and sends nothing
    assert refused.code == Code.INVALID_ARGUMENT
    assert refused.message.startswith(f"{rule.value}:")
    assert sim.commands == []


async def test_the_fleet_log_comes_back_as_a_replay_file(tmp_path: Path) -> None:
    # Given a session where the page applied a launch, refused a second launch, then applied a
    # switch of the active drone
    async with (
        a_fleet_station(tmp_path) as station,
        station.a_linked_page(
            Applies(seq=1, at_s=2.0),
            Refuses(at_s=5.0, reason="nest-ne-d1 is landing: launch needs a docked drone"),
            Applies(seq=3, at_s=12.5),
        ),
    ):
        await station.call("LaunchDrone", a_launch(SW_D1, THE_SHARED_ROUTE))
        await refusal_of(station, "LaunchDrone", a_launch(NE_D1, a_route((40.0, 90.0, 20.0))))
        await station.call("SetActiveDrone", making_active(SW_D1))

        # When the agent asks for the fleet log
        log = await station.call("GetFleetLog", pb.GetFleetLogRequest(scenario_id=SCENARIO))
        session = station.controller.session_id

    # Then it is the session's replay file, the --fleet-log lines the renderer reads
    assert isinstance(log, pb.GetFleetLogResponse)
    assert log.session_id == session
    assert log.fleet_log_jsonl == (FIXTURES / "fleet_link" / "session.fleet.jsonl").read_text(
        encoding="utf-8"
    )


# ---- the tools' other answers -----------------------------------------------------------------


async def test_list_nests_names_each_pad_and_its_drones(tmp_path: Path) -> None:
    # Given the station with the earthquake-fleet scenario
    async with a_fleet_station(tmp_path) as station:
        # When the agent lists the nests
        listed = await station.call("ListNests", pb.ListNestsRequest(scenario_id=SCENARIO))

    # Then each of the three nests comes with its pad, heading and drones
    assert isinstance(listed, pb.ListNestsResponse)
    assert [
        (n.id, (n.position.east, n.position.north, n.position.up), n.yaw_deg, tuple(n.drone_ids))
        for n in listed.nests
    ] == list(PADS)


UNKNOWN_SCENARIO: dict[str, tuple[str, object]] = {
    "list nests": ("ListNests", pb.ListNestsRequest(scenario_id="no-such-scene")),
    "list drones": ("ListDrones", the_drones("no-such-scene")),
    "launch": (
        "LaunchDrone",
        pb.LaunchDroneRequest(scenario_id="no-such-scene", drone_id=SW_D1, route=THE_SHARED_ROUTE),
    ),
}


@pytest.mark.parametrize(
    ("rpc", "request_"), UNKNOWN_SCENARIO.values(), ids=UNKNOWN_SCENARIO.keys()
)
async def test_an_unknown_scenario_is_not_found(tmp_path: Path, rpc: str, request_: object) -> None:
    # Given the station, which has no scenario no-such-scene
    async with a_fleet_station(tmp_path) as station:
        # When the agent names it
        refused = await refusal_of(station, rpc, request_)

    # Then the tool answers not found, naming the scenario
    assert refused.code == Code.NOT_FOUND
    assert "no-such-scene" in refused.message


async def test_an_unknown_drone_is_not_found(tmp_path: Path) -> None:
    # Given a linked page
    async with a_fleet_station(tmp_path) as station, station.a_linked_page() as sim:
        # When the agent launches a drone the scene does not have
        refused = await refusal_of(station, "LaunchDrone", a_launch("nest-zz-d9"))

    # Then the tool answers not found, and nothing reaches the page
    assert refused.code == Code.NOT_FOUND
    assert "nest-zz-d9" in refused.message
    assert sim.commands == []


async def test_a_command_the_page_refuses_fails_with_the_page_s_reason(tmp_path: Path) -> None:
    # Given a linked page that refuses the next command
    reason = "nest-sw-d1 is cruising: launch needs a docked drone"
    async with (
        a_fleet_station(tmp_path) as station,
        station.a_linked_page(Refuses(at_s=3.0, reason=reason)),
    ):
        # When the agent launches nest-sw-d1
        refused = await refusal_of(station, "LaunchDrone", a_launch())

    # Then the tool fails its precondition, in the page's own words
    assert refused.code == Code.FAILED_PRECONDITION
    assert refused.message == reason


async def test_a_page_that_never_answers_fails_the_command_past_its_deadline(
    tmp_path: Path,
) -> None:
    # Given a linked page that never answers, on an instant clock
    clock = RecordingSleep()
    async with a_fleet_station(tmp_path, timing=FleetTiming(sleep=clock)) as station:
        async with station.a_linked_page(StaysSilent()):
            # When the agent launches nest-sw-d1
            refused = await refusal_of(station, "LaunchDrone", a_launch())

    # Then the tool answers that its deadline passed
    assert refused.code == Code.DEADLINE_EXCEEDED


# ---- the contract -----------------------------------------------------------------------------


def test_every_fleet_tool_is_a_quick_call_that_fails_on_timeout() -> None:
    # When the fleet tools' contracts are built
    contracts = tool_contracts(FLEET_TOOLS)

    # Then there are nine, each run synchronously for up to 10 s and failed past it
    assert [c.name for c in contracts] == [
        "list_nests",
        "list_drones",
        "launch_drone",
        "set_route",
        "add_detour",
        "recall_drone",
        "set_active_drone",
        "get_fleet_log",
        "drone_map_status",
    ]
    assert {c.default_execution for c in contracts} == {
        ExecutionPolicy(mode=ExecutionMode.SYNC, timeout_s=10, on_timeout=OnTimeout.FAIL)
    }


def test_every_fleet_tool_is_described_to_the_model() -> None:
    # When the fleet tools' contracts are built
    contracts = tool_contracts(FLEET_TOOLS)

    # Then none is left without a description
    assert [c.name for c in contracts if not c.description] == []


# ---- unit: the error mapping ------------------------------------------------------------------


ERROR_CODES: dict[str, tuple[FleetError, Code]] = {
    "unknown drone": (
        FleetInvalid(InvalidRule.UNKNOWN_DRONE, "nest-zz-d9 is not a drone of this scene"),
        Code.NOT_FOUND,
    ),
    "invalid": (
        FleetInvalid(InvalidRule.NO_WAYPOINTS, "a route needs waypoints"),
        Code.INVALID_ARGUMENT,
    ),
    "refused": (
        FleetRefused("nest-sw-d1 is docked: detour needs a drone in flight"),
        Code.FAILED_PRECONDITION,
    ),
    "unavailable": (
        FleetUnavailable("no simulation connected for scenario quake-fleet"),
        Code.UNAVAILABLE,
    ),
    "timeout": (FleetTimeout("the page did not answer within 5.0 s"), Code.DEADLINE_EXCEEDED),
}


@pytest.mark.parametrize(("error", "code"), ERROR_CODES.values(), ids=ERROR_CODES.keys())
def test_each_fleet_failure_answers_its_connect_code(error: FleetError, code: Code) -> None:
    # When a failed command's error is mapped
    mapped = fleet_error(error)

    # Then it carries the code the agent reads it by
    assert mapped.code == code


def test_an_invalid_command_s_message_leads_with_its_rule() -> None:
    # Given a speed the station refused
    error = FleetInvalid(InvalidRule.SPEED_OUT_OF_RANGE, "speed 12.0 m/s is outside 0.5-8.0 m/s")

    # When it is mapped
    mapped = fleet_error(error)

    # Then the message names the rule, then the station's words
    assert mapped.message == "speed_out_of_range: speed 12.0 m/s is outside 0.5-8.0 m/s"


def test_a_refusal_keeps_the_page_s_reason_word_for_word() -> None:
    # Given a refusal in the page's words
    error = FleetRefused("nest-sw-d1 is docked: detour needs a drone in flight")

    # When it is mapped
    mapped = fleet_error(error)

    # Then the message is the page's reason, unchanged
    assert mapped.message == "nest-sw-d1 is docked: detour needs a drone in flight"


# ---- unit: requests become commands -----------------------------------------------------------


def test_a_flight_route_becomes_the_fleet_s_route() -> None:
    # When the shared route is converted
    route = flight_route(THE_SHARED_ROUTE)

    # Then it keeps its waypoints, speed and hover at the end
    assert route == Route(
        ((-20.0, 0.0, 15.0), (-20.0, 60.0, 18.0)), speed_m_s=6.0, on_complete="hover"
    )


def test_a_route_without_speed_or_end_leaves_the_simulation_s_defaults() -> None:
    # When a route with neither a speed nor an end is converted
    route = flight_route(a_route((0.0, 30.0, 12.0)))

    # Then both stay unset, so the simulation's own defaults apply
    assert route == Route(((0.0, 30.0, 12.0),), speed_m_s=None, on_complete=None)


def test_a_route_ending_in_return_says_so() -> None:
    # When a route that returns at its end is converted
    route = flight_route(a_route((0.0, 30.0, 12.0), on_complete=pb.ROUTE_END_RETURN))

    # Then it ends with a return
    assert route.on_complete == "return"


COMMANDS: dict[str, tuple[CommandRequest, FleetCommand]] = {
    "launch": (
        a_launch(SW_D1, a_route((0.0, 30.0, 12.0))),
        Launch(SW_D1, Route(((0.0, 30.0, 12.0),))),
    ),
    "set route": (
        a_new_route(SW_D1, a_route((10.0, 40.0, 20.0), speed_m_s=4.0)),
        SetRoute(SW_D1, Route(((10.0, 40.0, 20.0),), speed_m_s=4.0)),
    ),
    "detour": (a_detour(SW_D1, (0.0, 30.0, 12.0)), Detour(SW_D1, ((0.0, 30.0, 12.0),))),
    "recall": (a_recall(SW_D1), Recall(SW_D1)),
    "set active": (making_active(NE_D1), SetActive(NE_D1)),
}


@pytest.mark.parametrize(("request_", "command"), COMMANDS.values(), ids=COMMANDS.keys())
def test_each_command_request_becomes_its_fleet_command(
    request_: CommandRequest, command: FleetCommand
) -> None:
    # When the request is converted
    converted = fleet_command(request_)

    # Then it is the fleet command it asks for
    assert converted == command


# ---- unit: reports ----------------------------------------------------------------------------


PHASES: dict[Phase, pb.DronePhase] = {
    "docked": pb.DRONE_PHASE_DOCKED,
    "climbing": pb.DRONE_PHASE_CLIMBING,
    "cruising": pb.DRONE_PHASE_CRUISING,
    "detouring": pb.DRONE_PHASE_DETOURING,
    "hovering": pb.DRONE_PHASE_HOVERING,
    "returning": pb.DRONE_PHASE_RETURNING,
    "landing": pb.DRONE_PHASE_LANDING,
}


@pytest.mark.parametrize(("word", "phase"), PHASES.items(), ids=PHASES.keys())
def test_each_telemetry_phase_is_reported_as_its_drone_phase(
    word: Phase, phase: pb.DronePhase
) -> None:
    # When the page's phase word is converted
    converted = drone_phase(word)

    # Then it is the matching DronePhase
    assert converted == phase


SW_NEST = Nest("nest-sw", SW_PAD, 45.0, ("nest-sw-d1", "nest-sw-d2"))


def docked_on_sw_pad(drone: str) -> pb.DroneStatus:
    return pb.DroneStatus(
        id=drone, nest="nest-sw", phase=pb.DRONE_PHASE_DOCKED, position=enu(*SW_PAD), yaw_deg=45.0
    )


def test_a_nest_is_reported_with_its_pad_heading_and_drones() -> None:
    # When nest-sw is reported
    reported = fleet_nest(SW_NEST)

    # Then it carries its pad's centre, heading and drone ids
    assert reported == pb.FleetNest(
        id="nest-sw", position=enu(*SW_PAD), yaw_deg=45.0, drone_ids=["nest-sw-d1", "nest-sw-d2"]
    )


def test_drones_with_no_telemetry_are_docked_on_their_pad_facing_its_heading() -> None:
    # When nest-sw's drones are reported before any telemetry
    statuses = drone_statuses([SW_NEST], [])

    # Then both are docked at the pad, facing the pad's heading, with nothing left to fly
    assert list(statuses) == [docked_on_sw_pad("nest-sw-d1"), docked_on_sw_pad("nest-sw-d2")]


def test_a_drone_in_the_telemetry_is_reported_as_the_page_saw_it() -> None:
    # Given telemetry of nest-sw-d1 cruising
    seen = DroneTelemetry(SW_D1, "cruising", (-20.0, 10.0, 15.0), 90.0, 6.0, 2)

    # When nest-sw's drones are reported
    statuses = drone_statuses([SW_NEST], [seen])

    # Then nest-sw-d1 is as the page saw it, and its silent nest-mate is docked
    assert list(statuses) == [
        pb.DroneStatus(
            id=SW_D1,
            nest="nest-sw",
            phase=pb.DRONE_PHASE_CRUISING,
            position=enu(-20.0, 10.0, 15.0),
            yaw_deg=90.0,
            speed_m_s=6.0,
            targets_left=2,
        ),
        docked_on_sw_pad("nest-sw-d2"),
    ]


# ---- the drone map status ---------------------------------------------------------------------


def a_page_streaming_to_the_bridge(station: FleetStation) -> PerceptionRig:
    """A fleet page for quake-fleet connected to the station's stereo bridge (fake maps)."""
    return a_perception(station.rig.perception).opened(SCENARIO)


async def over_the_server(station: FleetStation, request: pb.DroneMapStatusRequest) -> object:
    """`DroneMapStatus` called on the running server's registered `FleetTools` service."""

    def post() -> pb.DroneMapStatusResponse:
        connection = http.client.HTTPConnection(station.address, timeout=10)
        try:
            connection.request(
                "POST",
                "/surmap.agent.v1.FleetTools/DroneMapStatus",
                body=request.SerializeToString(),
                headers={"content-type": "application/proto"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()
        assert response.status == 200, body.decode("utf-8", "replace")
        return pb.DroneMapStatusResponse.FromString(body)

    return await asyncio.to_thread(post)


def maps_in(status: object) -> list[tuple[str, int, int, int, bool]]:
    assert isinstance(status, pb.DroneMapStatusResponse)
    return [
        (d.drone_id, d.frames, d.keyframes, d.segmented_frames, d.processing) for d in status.drones
    ]


def map_status(drone: str | None = None, scenario: str = SCENARIO) -> pb.DroneMapStatusRequest:
    request = pb.DroneMapStatusRequest(scenario_id=scenario)
    if drone is not None:
        request.drone_id = drone
    return request


async def test_drone_map_status_reports_every_drone(tmp_path: Path) -> None:
    # Given a page streaming nest-sw-d1's frames, then nest-ne-d1's, to the station's bridge
    async with a_fleet_station(tmp_path) as station:
        page = a_page_streaming_to_the_bridge(station)
        page.streams(*blocks((SW_D1, 3), (NE_D1, 2)))

        # When the agent asks how each drone's map is doing
        status = await over_the_server(station, map_status())

    # Then every drone of the scene is reported in nest order, nest-ne-d1 the one processed now
    assert maps_in(status) == [
        (SW_D1, 3, 3, 3, False),
        ("nest-sw-d2", 0, 0, 0, False),
        (NE_D1, 2, 2, 2, True),
        ("nest-ne-d2", 0, 0, 0, False),
        ("nest-roof-d1", 0, 0, 0, False),
    ]


async def test_drone_map_status_for_one_drone_reports_only_it(tmp_path: Path) -> None:
    # Given a page that streamed nest-sw-d1's frames, then nest-ne-d1's
    async with a_fleet_station(tmp_path) as station:
        page = a_page_streaming_to_the_bridge(station)
        page.streams(*blocks((SW_D1, 3), (NE_D1, 2)))
        tool = drone_map_status_handler(station.rig.store, station.rig.perception)

        # When the agent asks about nest-sw-d1 alone
        status = await tool(map_status(SW_D1), None)

    # Then only its map is reported
    assert maps_in(status) == [(SW_D1, 3, 3, 3, False)]


async def test_drone_map_status_without_a_streaming_page_is_unavailable(tmp_path: Path) -> None:
    # Given the station with no page streaming to its bridge
    async with a_fleet_station(tmp_path) as station:
        tool = drone_map_status_handler(station.rig.store, station.rig.perception)

        # When the agent asks how the drones' maps are doing
        with pytest.raises(ConnectError) as raised:
            await tool(map_status(), None)

    # Then the tool answers unavailable
    assert raised.value.code == Code.UNAVAILABLE


DRONE_MAP_NOT_FOUND: dict[str, tuple[pb.DroneMapStatusRequest, str]] = {
    "unknown scenario": (map_status(scenario="no-such-scene"), "no-such-scene"),
    "unknown drone": (map_status("nest-zz-d9"), "nest-zz-d9"),
}


@pytest.mark.parametrize(
    ("request_", "named"), DRONE_MAP_NOT_FOUND.values(), ids=DRONE_MAP_NOT_FOUND.keys()
)
async def test_drone_map_status_for_what_the_scene_lacks_is_not_found(
    tmp_path: Path, request_: pb.DroneMapStatusRequest, named: str
) -> None:
    # Given a page streaming quake-fleet to the bridge
    async with a_fleet_station(tmp_path) as station:
        a_page_streaming_to_the_bridge(station)
        tool = drone_map_status_handler(station.rig.store, station.rig.perception)

        # When the agent names a scenario or drone the station does not have
        with pytest.raises(ConnectError) as raised:
            await tool(request_, None)

    # Then the tool answers not found, naming it
    assert (raised.value.code, named in raised.value.message) == (Code.NOT_FOUND, True)


def test_a_drone_s_counts_are_reported_field_for_field() -> None:
    # Given nest-ne-d1's session counts, it being the drone processed now
    counts = DroneCounts(
        drone_id=NE_D1,
        frames=412,
        posed=405,
        lost=7,
        keyframes=37,
        dropped=2,
        segmented_frames=380,
        detections=91,
        processing=True,
        last_t_ns=41_200_000_000,
    )

    # When they are reported
    reported = drone_map_counts(counts)

    # Then every count the tool describes is carried over
    assert reported == pb.DroneMapCounts(
        drone_id=NE_D1,
        frames=412,
        posed=405,
        lost=7,
        keyframes=37,
        segmented_frames=380,
        detections=91,
        processing=True,
        last_t_ns=41_200_000_000,
    )


def test_a_drone_that_has_not_streamed_reports_no_last_frame_time() -> None:
    # Given a session that has processed nothing yet
    counts = DroneCounts(
        drone_id=SW_D1,
        frames=0,
        posed=0,
        lost=0,
        keyframes=0,
        dropped=0,
        segmented_frames=0,
        detections=0,
        processing=False,
        last_t_ns=None,
    )

    # When it is reported
    reported = drone_map_counts(counts)

    # Then its last frame time is zero
    assert reported.last_t_ns == 0
