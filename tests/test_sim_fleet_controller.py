"""The station's fleet controller, registry and log store, without a server: what a command must
pass before it is sent, how a sent command waits for its answer, how pages link, and how the
applied commands are kept and exported as the renderer's `--fleet-log`."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from surmap.simulation.fleet.commands import (
    Detour,
    FleetCommand,
    Launch,
    Recall,
    Route,
    SetActive,
    SetRoute,
    Stamped,
    Waypoint,
)
from surmap.simulation.fleet.controller import (
    FleetController,
    FleetInvalid,
    FleetRefused,
    FleetRegistry,
    FleetTimeout,
    FleetTiming,
    FleetUnavailable,
    InvalidRule,
)
from surmap.simulation.fleet.link import (
    CLOSE_ALREADY_LINKED,
    CLOSE_PROTOCOL_ERROR,
    Applied,
    DroneTelemetry,
    Phase,
    Refused,
    SimHello,
    Telemetry,
)
from surmap.simulation.fleet.log_store import FleetLogStore, UnknownSession
from surmap.simulation.fleet_nests import nests_of
from surmap.simulation.scenario_manifest import load_presets
from surmap.simulation.scenario_store import ScenarioStore
from tests.fleet_fakes import (
    EARTHQUAKE_FLEET_DRONES,
    RecordingLink,
    RecordingSleep,
    ScriptedSocket,
    eventually,
    hello_frame,
    settle,
    telemetry_frame,
)
from tests.sim_fakes import POC_ASSETS

SCENARIO = "quake-fleet"
SW_D1 = "nest-sw-d1"
NE_D1 = "nest-ne-d1"
FIXTURES = Path(__file__).parent / "fixtures"
# The first command of `tests/fixtures/fleet/commands.json`.
THE_SHARED_LAUNCH = Launch(
    SW_D1, Route(((-20.0, 0.0, 15.0), (-20.0, 60.0, 18.0)), speed_m_s=6.0, on_complete="hover")
)


# ---- builders ---------------------------------------------------------------------------------


def a_controller(tmp_path: Path, timing: FleetTiming | None = None) -> FleetController:
    """The earthquake-fleet scenario's controller, not linked."""
    fleet = load_presets(POC_ASSETS)["earthquake-fleet"]
    store = FleetLogStore(tmp_path / "simulation.sqlite")
    return FleetController(SCENARIO, nests_of(fleet), store, timing=timing)


def a_linked_controller(
    tmp_path: Path, timing: FleetTiming | None = None
) -> tuple[FleetController, RecordingLink]:
    controller = a_controller(tmp_path, timing)
    link = RecordingLink()
    controller.attach(link, a_hello())
    return controller, link


def a_hello() -> SimHello:
    return SimHello(SCENARIO, 0.0, EARTHQUAKE_FLEET_DRONES)


def a_route(*waypoints: Waypoint, speed_m_s: float | None = None) -> Route:
    return Route(tuple(waypoints), speed_m_s=speed_m_s)


def a_launch(drone: str = SW_D1, *waypoints: Waypoint, speed_m_s: float | None = None) -> Launch:
    return Launch(drone, a_route(*(waypoints or ((-20.0, 0.0, 15.0),)), speed_m_s=speed_m_s))


def a_drone(drone: str, phase: Phase) -> DroneTelemetry:
    return DroneTelemetry(drone, phase, (-40.0, -20.0, 0.0), 45.0, 0.0, 0)


def telemetry_of(*drones: DroneTelemetry, at_s: float = 1.0, active: str = SW_D1) -> Telemetry:
    return Telemetry(at_s, active, drones)


def a_fleet_store(tmp_path: Path) -> ScenarioStore:
    """A scenario store holding the earthquake-fleet scenario `quake-fleet`."""
    store = ScenarioStore(
        db_path=tmp_path / "simulation.sqlite",
        library_dir=tmp_path / "library",
        presets=load_presets(POC_ASSETS),
    )
    store.create_scenario("Quake fleet", "earthquake-fleet")
    return store


async def answer(controller: FleetController, link: RecordingLink, seq: int, at_s: float) -> None:
    """The page applies the next frame the controller sent."""
    frame = await link.next_frame()
    controller.receive(Applied(frame["request"], seq, at_s))


# ---- what a command must pass before it is sent -----------------------------------------------

INVALID: dict[str, tuple[Phase, FleetCommand, InvalidRule]] = {
    "unknown drone": ("docked", a_launch("nest-zz-d9"), InvalidRule.UNKNOWN_DRONE),
    "unknown drone made active": ("docked", SetActive("nest-zz-d9"), InvalidRule.UNKNOWN_DRONE),
    "empty route": ("docked", Launch(SW_D1, Route(())), InvalidRule.NO_WAYPOINTS),
    "empty detour": ("cruising", Detour(SW_D1, ()), InvalidRule.NO_WAYPOINTS),
    "too slow": (
        "docked",
        a_launch(SW_D1, (0.0, 0.0, 15.0), speed_m_s=0.4),
        InvalidRule.SPEED_OUT_OF_RANGE,
    ),
    "too fast": (
        "cruising",
        SetRoute(SW_D1, a_route((0.0, 0.0, 15.0), speed_m_s=8.5)),
        InvalidRule.SPEED_OUT_OF_RANGE,
    ),
    "too low": ("docked", a_launch(SW_D1, (0.0, 0.0, 4.0)), InvalidRule.HEIGHT_OUT_OF_RANGE),
    "too high": (
        "cruising",
        Detour(SW_D1, ((0.0, 0.0, 61.0),)),
        InvalidRule.HEIGHT_OUT_OF_RANGE,
    ),
    "too far east": ("docked", a_launch(SW_D1, (501.0, 0.0, 15.0)), InvalidRule.OUT_OF_BOUNDS),
    "too far south": (
        "docked",
        a_launch(SW_D1, (0.0, 0.0, 15.0), (0.0, -501.0, 15.0)),
        InvalidRule.OUT_OF_BOUNDS,
    ),
    "launch in flight": ("cruising", a_launch(SW_D1), InvalidRule.NOT_DOCKED),
    "new route on the pad": (
        "docked",
        SetRoute(SW_D1, a_route((0.0, 0.0, 15.0))),
        InvalidRule.NOT_FLYING,
    ),
    "detour while landing": (
        "landing",
        Detour(SW_D1, ((0.0, 0.0, 15.0),)),
        InvalidRule.NOT_FLYING,
    ),
    "recall on the pad": ("docked", Recall(SW_D1), InvalidRule.ALREADY_DOCKED),
}


@pytest.mark.parametrize(("phase", "command", "rule"), INVALID.values(), ids=INVALID.keys())
async def test_an_invalid_command_names_the_rule_it_breaks(
    tmp_path: Path, phase: Phase, command: FleetCommand, rule: InvalidRule
) -> None:
    # Given a controller whose last telemetry has the drone in `phase`
    controller = a_controller(tmp_path)
    controller.receive(telemetry_of(a_drone(SW_D1, phase)))

    # When the command is sent
    with pytest.raises(FleetInvalid) as refused:
        await controller.send(command)

    # Then the station refuses it by the rule, before even asking whether a page is linked
    assert refused.value.rule is rule


async def test_before_any_telemetry_a_drone_counts_as_docked(tmp_path: Path) -> None:
    # Given a controller that has heard no telemetry
    controller = a_controller(tmp_path)

    # When a recall is sent
    with pytest.raises(FleetInvalid) as refused:
        await controller.send(Recall(SW_D1))

    # Then it is refused as a recall of a docked drone
    assert refused.value.rule is InvalidRule.ALREADY_DOCKED


async def test_the_limits_themselves_are_valid(tmp_path: Path) -> None:
    # Given a controller with no page linked
    controller = a_controller(tmp_path)

    # When a launch flies at the top speed through the corners of the allowed space
    launch = a_launch(SW_D1, (500.0, -500.0, 5.0), (-500.0, 500.0, 60.0), speed_m_s=8.0)

    # Then it passes every check and fails only for want of a page
    with pytest.raises(FleetUnavailable):
        await controller.send(launch)


async def test_without_a_page_a_valid_command_reports_no_simulation_connected(
    tmp_path: Path,
) -> None:
    # Given a controller with no page linked
    controller = a_controller(tmp_path)

    # When a valid launch is sent, then it fails naming the scenario
    with pytest.raises(FleetUnavailable, match="no simulation connected for scenario quake-fleet"):
        await controller.send(a_launch())


# ---- a sent command waits for its answer ------------------------------------------------------


async def test_an_applied_command_returns_the_simulations_stamp(tmp_path: Path) -> None:
    # Given a linked controller
    controller, link = a_linked_controller(tmp_path)

    # When a launch is sent and the page applies it as entry 1 at 2.5 s
    sending = asyncio.create_task(controller.send(a_launch()))
    await answer(controller, link, seq=1, at_s=2.5)
    applied = await sending

    # Then the controller returns the page's stamp, and the session log holds the launch
    assert applied == Applied(request=1, seq=1, at_s=2.5)
    assert controller.session_log() == (Stamped(1, 2.5, a_launch()),)


async def test_the_station_sends_the_command_itself(tmp_path: Path) -> None:
    # Given a linked controller
    controller, link = a_linked_controller(tmp_path)

    # When the drone is made active
    sending = asyncio.create_task(controller.send(SetActive(NE_D1)))
    await answer(controller, link, seq=1, at_s=3.0)
    await sending

    # Then the page received exactly that command as request 1
    assert link.sent == [
        {"type": "command", "request": 1, "command": {"type": "set_active", "drone": NE_D1}}
    ]


async def test_requests_are_numbered_from_one_in_the_order_they_are_sent(tmp_path: Path) -> None:
    # Given a linked controller
    controller, link = a_linked_controller(tmp_path)

    # When two commands are sent one after the other, each applied
    first = asyncio.create_task(controller.send(SetActive(NE_D1)))
    await answer(controller, link, seq=1, at_s=1.0)
    await first
    second = asyncio.create_task(controller.send(SetActive(SW_D1)))
    await answer(controller, link, seq=2, at_s=2.0)
    await second

    # Then their requests are 1 and 2
    assert [frame["request"] for frame in link.sent] == [1, 2]


async def test_a_command_is_sent_only_once_the_one_before_it_is_answered(tmp_path: Path) -> None:
    # Given a linked controller with one command already waiting for its answer
    controller, link = a_linked_controller(tmp_path)
    first = asyncio.create_task(controller.send(SetActive(NE_D1)))
    await link.next_frame()

    # When a second command is sent meanwhile
    second = asyncio.create_task(controller.send(SetActive(SW_D1)))
    await settle()

    # Then it is held back until the first is applied
    assert len(link.sent) == 1
    controller.receive(Applied(1, 1, 1.0))
    await answer(controller, link, seq=2, at_s=2.0)
    assert [await first, await second] == [Applied(1, 1, 1.0), Applied(2, 2, 2.0)]


async def test_a_refused_command_raises_the_simulations_reason_and_is_not_logged(
    tmp_path: Path,
) -> None:
    # Given a linked controller
    controller, link = a_linked_controller(tmp_path)

    # When the page refuses the launch
    sending = asyncio.create_task(controller.send(a_launch()))
    frame = await link.next_frame()
    controller.receive(
        Refused(frame["request"], 4.0, "nest-sw-d1 is climbing: launch needs a docked drone")
    )

    # Then the controller raises the page's reason, and logs nothing
    with pytest.raises(FleetRefused, match="nest-sw-d1 is climbing: launch needs a docked drone"):
        await sending
    assert controller.session_log() == ()


async def test_a_silent_page_times_out_after_five_seconds(tmp_path: Path) -> None:
    # Given a linked page that never answers, and a clock that remembers every wait
    sleep = RecordingSleep()
    controller, _link = a_linked_controller(tmp_path, FleetTiming(sleep=sleep))

    # When a command is sent, then it times out
    with pytest.raises(FleetTimeout):
        await controller.send(a_launch())

    # And it waited five seconds for the answer
    assert sleep.waits == [5.0]


async def test_a_page_that_unlinks_fails_the_waiting_command_as_no_simulation_connected(
    tmp_path: Path,
) -> None:
    # Given a linked controller waiting for an answer
    controller, link = a_linked_controller(tmp_path)
    sending = asyncio.create_task(controller.send(a_launch()))
    await link.next_frame()

    # When the page unlinks
    controller.detach()

    # Then the waiting command reports no simulation connected
    with pytest.raises(FleetUnavailable):
        await sending


# ---- telemetry --------------------------------------------------------------------------------


async def test_before_any_telemetry_the_controller_reports_no_drones(tmp_path: Path) -> None:
    # Given a controller that has heard nothing
    controller = a_controller(tmp_path)

    # Then it reports no drone and no active one
    assert (controller.drones(), controller.active()) == ((), None)


async def test_the_latest_telemetry_is_what_the_controller_reports(tmp_path: Path) -> None:
    # Given a controller that heard two telemetry frames
    controller = a_controller(tmp_path)
    controller.receive(telemetry_of(a_drone(SW_D1, "docked"), at_s=1.0, active=SW_D1))
    controller.receive(telemetry_of(a_drone(SW_D1, "climbing"), at_s=1.5, active=NE_D1))

    # Then it reports the second
    assert (controller.drones(), controller.active()) == ((a_drone(SW_D1, "climbing"),), NE_D1)


# ---- the registry links pages -----------------------------------------------------------------


def test_the_registry_keeps_one_controller_per_scenario(tmp_path: Path) -> None:
    # Given a registry over the earthquake-fleet scenario
    registry = FleetRegistry(a_fleet_store(tmp_path))

    # When its controller is asked for twice
    first, again = registry.controller(SCENARIO), registry.controller(SCENARIO)

    # Then it is the same controller, for that scenario
    assert (first is again, first.scenario_id) == (True, SCENARIO)


async def test_a_page_that_says_hello_is_linked_until_it_hangs_up(tmp_path: Path) -> None:
    # Given a page that says hello
    registry = FleetRegistry(a_fleet_store(tmp_path))
    page = ScriptedSocket()
    page.say(hello_frame(SCENARIO))
    linking = asyncio.create_task(registry.link(SCENARIO, page))
    await eventually(lambda: registry.controller(SCENARIO).linked)

    # When it hangs up
    page.hang_up()
    await linking

    # Then the scenario is no longer linked
    assert registry.controller(SCENARIO).linked is False


async def test_telemetry_a_linked_page_sends_reaches_its_controller(tmp_path: Path) -> None:
    # Given a linked page
    registry = FleetRegistry(a_fleet_store(tmp_path))
    page = ScriptedSocket()
    page.say(hello_frame(SCENARIO))
    linking = asyncio.create_task(registry.link(SCENARIO, page))

    # When it reports its drones with the north-east drone active
    page.say(telemetry_frame(2.0, NE_D1))
    await eventually(lambda: registry.controller(SCENARIO).active() == NE_D1)
    page.hang_up()
    await linking

    # Then the scenario's controller has heard it
    assert registry.controller(SCENARIO).active() == NE_D1


async def test_a_second_page_for_a_linked_scenario_is_closed_as_already_linked(
    tmp_path: Path,
) -> None:
    # Given a scenario with a linked page
    registry = FleetRegistry(a_fleet_store(tmp_path))
    first = ScriptedSocket()
    first.say(hello_frame(SCENARIO))
    linking = asyncio.create_task(registry.link(SCENARIO, first))
    await eventually(lambda: registry.controller(SCENARIO).linked)

    # When a second page links the same scenario
    second = ScriptedSocket()
    second.say(hello_frame(SCENARIO))
    await registry.link(SCENARIO, second)

    # Then the second is closed as already linked, and the first stays linked
    assert (await second.close_code(), first.closed_with) == (CLOSE_ALREADY_LINKED, None)
    assert registry.controller(SCENARIO).linked is True
    first.hang_up()
    await linking


NOT_A_HELLO = {
    "telemetry first": telemetry_frame(0.5, None),
    "another protocol": hello_frame(SCENARIO, protocol="fleet/v2"),
}


@pytest.mark.parametrize("opening", NOT_A_HELLO.values(), ids=NOT_A_HELLO.keys())
async def test_a_page_that_does_not_open_with_a_fleet_v1_hello_is_closed_as_a_protocol_error(
    tmp_path: Path, opening: dict[str, object]
) -> None:
    # Given a page whose first frame is not a fleet/v1 hello
    registry = FleetRegistry(a_fleet_store(tmp_path))
    page = ScriptedSocket()
    page.say(opening)

    # When it links
    await registry.link(SCENARIO, page)

    # Then it is closed as a protocol error and never linked
    assert (await page.close_code(), registry.controller(SCENARIO).linked) == (
        CLOSE_PROTOCOL_ERROR,
        False,
    )


async def test_an_unknown_frame_after_hello_closes_the_link_as_a_protocol_error(
    tmp_path: Path,
) -> None:
    # Given a linked page
    registry = FleetRegistry(a_fleet_store(tmp_path))
    page = ScriptedSocket()
    page.say(hello_frame(SCENARIO))
    linking = asyncio.create_task(registry.link(SCENARIO, page))

    # When it sends a frame fleet/v1 does not have
    page.say_text('{"type":"self_destruct"}')
    await linking

    # Then the link is closed as a protocol error and the scenario unlinked
    assert (page.closed_with, registry.controller(SCENARIO).linked) == (
        CLOSE_PROTOCOL_ERROR,
        False,
    )


# ---- the log store ----------------------------------------------------------------------------


def test_a_stored_session_exports_as_the_fleet_log_file_the_renderer_reads(
    tmp_path: Path,
) -> None:
    # Given a session that applied a launch as entry 1 and a set_active as entry 3
    store = FleetLogStore(tmp_path / "simulation.sqlite")
    session = store.start_session(SCENARIO, a_hello())
    store.record(session, Stamped(1, 2.0, THE_SHARED_LAUNCH))
    store.record(session, Stamped(3, 12.5, SetActive(SW_D1)))

    # When it is exported
    exported = store.export_jsonl(session)

    # Then the export is the shared station-export fixture, line for line
    assert exported == (FIXTURES / "fleet_link" / "session.fleet.jsonl").read_text(encoding="utf-8")


def test_entries_come_back_in_simulation_time_order(tmp_path: Path) -> None:
    # Given entries recorded out of time order
    store = FleetLogStore(tmp_path / "simulation.sqlite")
    session = store.start_session(SCENARIO, a_hello())
    store.record(session, Stamped(2, 5.0, SetActive(NE_D1)))
    store.record(session, Stamped(1, 2.0, SetActive(SW_D1)))

    # When the session's entries are read
    entries = store.entries(session)

    # Then they are in simulation-time order
    assert [entry.seq for entry in entries] == [1, 2]


def test_each_linked_page_is_its_own_session(tmp_path: Path) -> None:
    # Given two sessions of the scenario, the first with one entry
    store = FleetLogStore(tmp_path / "simulation.sqlite")
    first = store.start_session(SCENARIO, a_hello())
    store.record(first, Stamped(1, 2.0, SetActive(NE_D1)))
    second = store.start_session(SCENARIO, SimHello(SCENARIO, 30.0, EARTHQUAKE_FLEET_DRONES))

    # When the scenario's sessions are listed
    sessions = store.sessions(SCENARIO)

    # Then both are listed oldest first with their hellos, and the second has no entries
    assert [(s.session_id, s.hello.sim_t_s) for s in sessions] == [(first, 0.0), (second, 30.0)]
    assert store.entries(second) == ()


def test_an_unknown_session_has_no_entries(tmp_path: Path) -> None:
    # Given an empty log store
    store = FleetLogStore(tmp_path / "simulation.sqlite")

    # When an unknown session is read, then it is refused
    with pytest.raises(UnknownSession):
        store.entries(999)


def test_the_fleet_tables_live_in_the_scenario_file_beside_its_scenarios(tmp_path: Path) -> None:
    # Given a scenario store holding a scenario
    scenarios = a_fleet_store(tmp_path)

    # When a fleet session is kept in the same file
    FleetLogStore(scenarios.db_path).start_session(SCENARIO, a_hello())

    # Then the file has the fleet tables, and the scenario is still there
    with sqlite3.connect(scenarios.db_path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"fleet_sessions", "fleet_log"} <= tables
    assert scenarios.scenario(SCENARIO).id == SCENARIO
