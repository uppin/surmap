"""`fleet/v1` on the station's side: the goldens the renderer's `fleet/link.rs` shares decode and
re-encode byte for byte, and the station's commands are exactly the renderer's `FleetCommand`
JSON (`tests/fixtures/fleet/commands.json`)."""

from __future__ import annotations

import json
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
    command_json,
    parse_command,
)
from surmap.simulation.fleet.link import (
    Applied,
    DroneTelemetry,
    FleetLinkError,
    Refused,
    SimHello,
    SimMessage,
    Telemetry,
    decode_sim_message,
    encode_command,
    encode_sim_message,
)

FIXTURES = Path(__file__).parent / "fixtures"


def golden(name: str) -> str:
    """A golden frame as sent: the file without its trailing newline."""
    return (FIXTURES / "fleet_link" / name).read_text(encoding="utf-8").rstrip("\n")


def the_shared_commands() -> list[dict[str, object]]:
    loaded: list[dict[str, object]] = json.loads(
        (FIXTURES / "fleet" / "commands.json").read_text(encoding="utf-8")
    )
    return loaded


THE_SHARED_LAUNCH = Launch(
    "nest-sw-d1",
    Route(((-20.0, 0.0, 15.0), (-20.0, 60.0, 18.0)), speed_m_s=6.0, on_complete="hover"),
)

# The five commands of `tests/fixtures/fleet/commands.json`, in order.
THE_SHARED_COMMANDS: tuple[FleetCommand, ...] = (
    THE_SHARED_LAUNCH,
    SetRoute("nest-sw-d1", Route(((10.0, 40.0, 20.0),))),
    Detour("nest-sw-d1", ((0.0, 35.0, 18.0), (5.0, 45.0, 18.0))),
    Recall("nest-sw-d1"),
    SetActive("nest-ne-d1"),
)

THE_GOLDEN_MESSAGES: list[tuple[str, SimMessage]] = [
    (
        "hello.json",
        SimHello(
            "quake-fleet",
            0.0,
            ("nest-sw-d1", "nest-sw-d2", "nest-ne-d1", "nest-ne-d2", "nest-roof-d1"),
        ),
    ),
    ("applied.json", Applied(request=7, seq=3, at_s=41.25)),
    (
        "refused.json",
        Refused(
            request=7, at_s=41.25, reason="nest-sw-d1 is docked: detour needs a drone in flight"
        ),
    ),
    (
        "telemetry.json",
        Telemetry(
            41.5,
            "nest-sw-d1",
            (
                DroneTelemetry("nest-sw-d1", "cruising", (-20.0, 12.5, 15.0), 90.0, 6.0, 2),
                DroneTelemetry("nest-sw-d2", "docked", (-40.0, -20.0, 0.0), 45.0, 0.0, 0),
            ),
        ),
    ),
]


@pytest.mark.parametrize(
    ("name", "expected"), THE_GOLDEN_MESSAGES, ids=[n for n, _ in THE_GOLDEN_MESSAGES]
)
def test_every_simulation_golden_decodes_into_its_message(name: str, expected: SimMessage) -> None:
    # Given a frame the simulation sends
    frame = golden(name)

    # When the station decodes it
    message = decode_sim_message(frame)

    # Then it is the message the golden describes
    assert message == expected


@pytest.mark.parametrize("name", [n for n, _ in THE_GOLDEN_MESSAGES])
def test_every_simulation_golden_reencodes_byte_identically(name: str) -> None:
    # Given a decoded simulation golden
    message = decode_sim_message(golden(name))

    # When it is written again
    frame = encode_sim_message(message)

    # Then it is the golden, byte for byte
    assert frame == golden(name)


def test_the_station_sends_the_command_golden_for_the_shared_launch() -> None:
    # When the station sends the shared fixture's launch as request 7
    frame = encode_command(7, THE_SHARED_LAUNCH)

    # Then the frame is the command golden, byte for byte
    assert frame == golden("command.json")


def test_every_station_command_serialises_to_the_renderers_shared_fixture() -> None:
    # When the five station commands are written as renderer commands
    written = [command_json(command) for command in THE_SHARED_COMMANDS]

    # Then they are the shared fixture, a route without speed or on_complete leaving them out
    assert written == the_shared_commands()


def test_every_command_of_the_shared_fixture_reads_back_as_its_station_command() -> None:
    # Given the renderer's shared command fixture
    shared = the_shared_commands()

    # When each entry is read as a station command
    commands = tuple(parse_command(entry) for entry in shared)

    # Then they are the five station commands
    assert commands == THE_SHARED_COMMANDS


def test_a_command_of_an_unknown_type_does_not_read() -> None:
    # Given an entry whose type no fleet command has
    entry = {"type": "self_destruct", "drone": "nest-sw-d1"}

    # When it is read, then it is refused
    with pytest.raises(ValueError, match="self_destruct"):
        parse_command(entry)


NOT_FLEET_V1 = {
    "not JSON": "applied 7",
    "an unknown type": '{"type":"self_destruct","request":7}',
    "another protocol": (
        '{"type":"hello","protocol":"fleet/v2","scenario":"quake-fleet","sim_t_s":0.0,"drones":[]}'
    ),
    "a missing field": '{"type":"applied","request":7,"at_s":41.25}',
    "an unknown phase": (
        '{"type":"telemetry","sim_t_s":1.0,"active":null,"drones":[{"id":"nest-sw-d1",'
        '"phase":"teleporting","enu":[0.0,0.0,0.0],"yaw_deg":0.0,"speed_m_s":0.0,"targets_left":0}]}'
    ),
}


@pytest.mark.parametrize("frame", NOT_FLEET_V1.values(), ids=NOT_FLEET_V1.keys())
def test_a_frame_that_is_not_fleet_v1_is_a_link_error(frame: str) -> None:
    # When the station decodes a frame that breaks the protocol, then it is a link error
    with pytest.raises(FleetLinkError):
        decode_sim_message(frame)
