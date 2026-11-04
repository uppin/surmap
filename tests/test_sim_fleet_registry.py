"""The station's fleet registry: one controller per scenario, and how a page links it — the
`hello` it must open with, the frames it may send after, and the one page a scenario takes."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from surmap.simulation.fleet.commands import Launch, Route
from surmap.simulation.fleet.controller import FleetUnavailable
from surmap.simulation.fleet.link import CLOSE_ALREADY_LINKED, CLOSE_PROTOCOL_ERROR
from surmap.simulation.fleet.registry import FleetRegistry
from surmap.simulation.manifest_checks import object_list
from surmap.simulation.scenario_store import ScenarioStore
from tests.fleet_fakes import (
    QUAKE_FLEET,
    ScriptedSocket,
    a_fleet_store,
    eventually,
    hello_frame,
    telemetry_frame,
)

SCENARIO = QUAKE_FLEET
NE_D1 = "nest-ne-d1"


def with_a_new_nest(store: ScenarioStore, nest_id: str, at: tuple[float, float, float]) -> None:
    """Saves the scenario's next version with one more one-drone nest, `nest_id`, at `at`."""
    manifest = store.scenario(SCENARIO).manifest
    nest: dict[str, object] = {"kind": "drone_nest", "id": nest_id, "position_enu": list(at)}
    store.save(SCENARIO, {**manifest, "elements": [*object_list(manifest, "elements"), nest]})


def a_launch_of(drone: str) -> Launch:
    return Launch(drone, Route(((-20.0, 0.0, 15.0),)))


# ---- the registry links pages -----------------------------------------------------------------


async def test_a_page_that_links_an_unknown_scenario_is_closed_as_a_protocol_error(
    tmp_path: Path,
) -> None:
    # Given a registry that has no scenario `no-such-scenario`
    registry = FleetRegistry(a_fleet_store(tmp_path))
    page = ScriptedSocket()
    page.say(hello_frame("no-such-scenario"))

    # When a page links it
    await registry.link("no-such-scenario", page)

    # Then it is closed as a protocol error
    assert await page.close_code() == CLOSE_PROTOCOL_ERROR


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


async def test_a_page_whose_hello_names_another_scenario_is_refused(tmp_path: Path) -> None:
    # Given a page linking quake-fleet whose hello names another scenario
    registry = FleetRegistry(a_fleet_store(tmp_path))
    page = ScriptedSocket()
    page.say(hello_frame("harbour-fleet"))
    page.hang_up()

    # When it links
    await registry.link(SCENARIO, page)

    # Then it is closed as a protocol error, and quake-fleet never started a session for it
    assert (page.closed_with, registry.log_store.sessions(SCENARIO)) == (CLOSE_PROTOCOL_ERROR, ())


async def test_a_nest_added_after_the_first_call_has_drones_the_controller_knows(
    tmp_path: Path,
) -> None:
    # Given a registry whose quake-fleet controller is already in use
    store = a_fleet_store(tmp_path)
    registry = FleetRegistry(store)
    registry.controller(SCENARIO)

    # When the scenario gains a nest, and its new drone is launched with no page linked
    with_a_new_nest(store, "nest-new", (0.0, -60.0, 0.0))
    launching = registry.controller(SCENARIO).send(a_launch_of("nest-new-d1"))

    # Then the launch fails for want of a page, not as an unknown drone
    with pytest.raises(FleetUnavailable):
        await launching
