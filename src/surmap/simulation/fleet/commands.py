"""The fleet commands the station sends, as the renderer's `FleetCommand` (n2) reads them.

A command's JSON is exactly an entry of `tests/fixtures/fleet/commands.json`: a `type` tag, the
`drone` id, then the command's own fields. A `Route` with no `speed_m_s` or `on_complete` omits
them, and the simulation fills its defaults (`DEFAULT_SPEED_M_S`, `"return"`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "BOUND_M",
    "DEFAULT_SPEED_M_S",
    "MAX_SPEED_M_S",
    "MAX_UP_M",
    "MIN_SPEED_M_S",
    "MIN_UP_M",
    "Detour",
    "FleetCommand",
    "Launch",
    "OnComplete",
    "Recall",
    "Route",
    "SetActive",
    "SetRoute",
    "Stamped",
    "Waypoint",
    "command_json",
    "parse_command",
]

# The renderer's autopilot limits (`fleet/autopilot.rs`), checked again by the station.
MIN_SPEED_M_S = 0.5
MAX_SPEED_M_S = 8.0
DEFAULT_SPEED_M_S = 5.0
MIN_UP_M = 5.0
MAX_UP_M = 60.0
# A waypoint lies within ±BOUND_M east and north of the scene origin.
BOUND_M = 500.0

Waypoint = tuple[float, float, float]
"""East, north, up, in metres."""

OnComplete = Literal["return", "hover"]


@dataclass(frozen=True)
class Route:
    """Waypoints flown in order at `speed_m_s`, then `on_complete`; `None` leaves the
    simulation's default and is not written."""

    waypoints: tuple[Waypoint, ...]
    speed_m_s: float | None = None
    on_complete: OnComplete | None = None


@dataclass(frozen=True)
class Launch:
    """Take off from the pad and fly `route`."""

    drone: str
    route: Route


@dataclass(frozen=True)
class SetRoute:
    """Replace the remaining targets, from where the drone is."""

    drone: str
    route: Route


@dataclass(frozen=True)
class Detour:
    """Visit `waypoints`, then resume the target that was current."""

    drone: str
    waypoints: tuple[Waypoint, ...]


@dataclass(frozen=True)
class Recall:
    """Fly back above the pad, land and dock."""

    drone: str


@dataclass(frozen=True)
class SetActive:
    """Show this drone's eyes, and record its pose, from the time it applies."""

    drone: str


FleetCommand = Launch | SetRoute | Detour | Recall | SetActive


@dataclass(frozen=True)
class Stamped:
    """A command the simulation applied: its `seq` and the simulation time it took effect."""

    seq: int
    at_s: float
    command: FleetCommand


def command_json(command: FleetCommand) -> dict[str, object]:
    """`command` as the renderer's `FleetCommand` JSON object (key order: `type`, `drone`, then
    the command's fields)."""
    # TODO(pr-3): implement
    raise NotImplementedError("pr-3: implement")


def parse_command(data: Mapping[str, object]) -> FleetCommand:
    """The command `data` describes; `ValueError` when it is not a fleet command."""
    # TODO(pr-3): implement
    raise NotImplementedError("pr-3: implement")
