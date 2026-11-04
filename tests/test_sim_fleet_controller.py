"""The station's fleet controller, without a server or a registry: what a command must pass
before it is sent, how a sent command waits for its answer, and what the controller reports from
the page's telemetry."""

from __future__ import annotations

import asyncio
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
    FleetTimeout,
    FleetTiming,
    FleetUnavailable,
    InvalidRule,
)
from surmap.simulation.fleet.link import (
    Applied,
    DroneTelemetry,
    Phase,
    Refused,
    SimHello,
    Telemetry,
)
from surmap.simulation.fleet.log_store import FleetLogStore
from surmap.simulation.fleet_nests import nests_of
from surmap.simulation.scenario_manifest import load_presets
from tests.fleet_fakes import (
    QUAKE_FLEET,
    RecordingLink,
    RecordingSleep,
    a_hello,
    settle,
)
from tests.sim_fakes import POC_ASSETS

SCENARIO = QUAKE_FLEET
SW_D1 = "nest-sw-d1"
NE_D1 = "nest-ne-d1"


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


def a_route(*waypoints: Waypoint, speed_m_s: float | None = None) -> Route:
    return Route(tuple(waypoints), speed_m_s=speed_m_s)


def a_launch(drone: str = SW_D1, *waypoints: Waypoint, speed_m_s: float | None = None) -> Launch:
    return Launch(drone, a_route(*(waypoints or ((-20.0, 0.0, 15.0),)), speed_m_s=speed_m_s))


def a_drone(drone: str, phase: Phase) -> DroneTelemetry:
    return DroneTelemetry(drone, phase, (-40.0, -20.0, 0.0), 45.0, 0.0, 0)


def telemetry_of(*drones: DroneTelemetry, at_s: float = 1.0, active: str = SW_D1) -> Telemetry:
    return Telemetry(at_s, active, drones)


async def answer(controller: FleetController, link: RecordingLink, seq: int, at_s: float) -> None:
    """The page applies the next frame the controller sent."""
    frame = await link.next_frame()
    controller.receive(Applied(frame["request"], seq, at_s))


def commands_sent(link: RecordingLink) -> list[str]:
    """The type of each command the page received, in order."""
    return [frame["command"]["type"] for frame in link.sent]


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


async def test_a_drone_just_launched_can_be_tasked_before_telemetry_shows_it_flying(
    tmp_path: Path,
) -> None:
    # Given a linked controller whose last telemetry still has the drone docked
    controller, link = a_linked_controller(tmp_path)
    controller.receive(telemetry_of(a_drone(SW_D1, "docked"), at_s=1.0))

    # When the page applies a launch at 2.0 s, and a detour is sent straight after it
    launching = asyncio.create_task(controller.send(a_launch()))
    await answer(controller, link, seq=1, at_s=2.0)
    await launching
    detouring = asyncio.create_task(controller.send(Detour(SW_D1, ((0.0, 35.0, 18.0),))))
    await answer(controller, link, seq=2, at_s=2.1)

    # Then the station does not refuse the detour as one for a docked drone
    assert await detouring == Applied(request=2, seq=2, at_s=2.1)


async def test_telemetry_taken_after_a_launch_decides_the_drones_phase_again(
    tmp_path: Path,
) -> None:
    # Given a controller whose page applied a launch at 2.0 s
    controller, link = a_linked_controller(tmp_path)
    launching = asyncio.create_task(controller.send(a_launch()))
    await answer(controller, link, seq=1, at_s=2.0)
    await launching

    # When telemetry from 2.5 s reports the drone docked again
    controller.receive(telemetry_of(a_drone(SW_D1, "docked"), at_s=2.5))

    # Then a detour is refused as one for a docked drone
    with pytest.raises(FleetInvalid) as refused:
        await controller.send(Detour(SW_D1, ((0.0, 35.0, 18.0),)))
    assert refused.value.rule is InvalidRule.NOT_FLYING


async def test_telemetry_from_the_frame_a_launch_lands_in_keeps_the_drone_climbing(
    tmp_path: Path,
) -> None:
    # Given a controller whose page applied a launch at 1.02 s, which takes effect at the
    # page's next 0.05 s step (1.05 s)
    controller, link = a_linked_controller(tmp_path)
    launching = asyncio.create_task(controller.send(a_launch()))
    await answer(controller, link, seq=1, at_s=1.02)
    await launching

    # When telemetry stamped 1.02 s, from before that step, still has the drone docked
    controller.receive(telemetry_of(a_drone(SW_D1, "docked"), at_s=1.02))
    recalling = asyncio.create_task(controller.send(Recall(SW_D1)))
    await settle()

    # Then a recall passes the station's check and reaches the page
    assert commands_sent(link) == ["launch", "recall"]
    await answer(controller, link, seq=2, at_s=1.1)
    assert await recalling == Applied(request=2, seq=2, at_s=1.1)


async def test_a_command_applied_after_the_station_gave_up_on_it_is_still_logged(
    tmp_path: Path,
) -> None:
    # Given a linked page whose answer arrives after the ack timeout
    controller, link = a_linked_controller(tmp_path, FleetTiming(sleep=RecordingSleep()))
    with pytest.raises(FleetTimeout):
        await controller.send(a_launch())
    frame = await link.next_frame()

    # When the page's `applied` finally arrives
    controller.receive(Applied(frame["request"], 1, 7.0))

    # Then the launch is in the session log, as the page applied it
    assert controller.session_log() == (Stamped(1, 7.0, a_launch()),)


async def test_a_linked_pages_own_drones_are_the_ones_the_station_knows(tmp_path: Path) -> None:
    # Given a controller whose page says hello with a drone the scenario's nests do not name
    controller = a_controller(tmp_path)
    link = RecordingLink()
    controller.attach(link, SimHello(SCENARIO, 0.0, ("nest-new-d1",)))

    # When that drone is made active and the page applies it
    sending = asyncio.create_task(controller.send(SetActive("nest-new-d1")))
    await answer(controller, link, seq=1, at_s=1.0)

    # Then the station sent it, rather than refusing an unknown drone
    assert await sending == Applied(request=1, seq=1, at_s=1.0)


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
