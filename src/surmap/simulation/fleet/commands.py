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


def _waypoints_json(waypoints: tuple[Waypoint, ...]) -> list[list[float]]:
    return [[float(east), float(north), float(up)] for east, north, up in waypoints]


def _route_json(route: Route) -> dict[str, object]:
    written: dict[str, object] = {"waypoints": _waypoints_json(route.waypoints)}
    if route.speed_m_s is not None:
        written["speed_m_s"] = float(route.speed_m_s)
    if route.on_complete is not None:
        written["on_complete"] = route.on_complete
    return written


def command_json(command: FleetCommand) -> dict[str, object]:
    """`command` as the renderer's `FleetCommand` JSON object (key order: `type`, `drone`, then
    the command's fields)."""
    match command:
        case Launch(drone, route):
            return {"type": "launch", "drone": drone, "route": _route_json(route)}
        case SetRoute(drone, route):
            return {"type": "set_route", "drone": drone, "route": _route_json(route)}
        case Detour(drone, waypoints):
            return {"type": "detour", "drone": drone, "waypoints": _waypoints_json(waypoints)}
        case Recall(drone):
            return {"type": "recall", "drone": drone}
        case SetActive(drone):
            return {"type": "set_active", "drone": drone}


def _text(data: Mapping[str, object], key: str, what: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{what}: {key!r} must be a string")
    return value


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{what} must be a number")
    return float(value)


def _waypoints(value: object, what: str) -> tuple[Waypoint, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{what}: 'waypoints' must be a list")
    found: list[Waypoint] = []
    for point in value:
        if not isinstance(point, list) or len(point) != 3:
            raise ValueError(f"{what}: a waypoint is [east, north, up]")
        east, north, up = (_number(axis, f"{what}: a waypoint coordinate") for axis in point)
        found.append((east, north, up))
    return tuple(found)


def _route(value: object, what: str) -> Route:
    if not isinstance(value, Mapping):
        raise ValueError(f"{what}: 'route' must be an object")
    speed = value.get("speed_m_s")
    on_complete: OnComplete | None
    match value.get("on_complete"):
        case None:
            on_complete = None
        case "return":
            on_complete = "return"
        case "hover":
            on_complete = "hover"
        case _:
            raise ValueError(f"{what}: on_complete must be 'return' or 'hover'")
    return Route(
        _waypoints(value.get("waypoints"), what),
        speed_m_s=None if speed is None else _number(speed, f"{what}: speed_m_s"),
        on_complete=on_complete,
    )


def parse_command(data: Mapping[str, object]) -> FleetCommand:
    """The command `data` describes; `ValueError` when it is not a fleet command."""
    kind = data.get("type")
    what = f"command {kind!r}"
    match kind:
        case "launch":
            return Launch(_text(data, "drone", what), _route(data.get("route"), what))
        case "set_route":
            return SetRoute(_text(data, "drone", what), _route(data.get("route"), what))
        case "detour":
            return Detour(_text(data, "drone", what), _waypoints(data.get("waypoints"), what))
        case "recall":
            return Recall(_text(data, "drone", what))
        case "set_active":
            return SetActive(_text(data, "drone", what))
        case _:
            raise ValueError(f"unknown fleet command type {kind!r}")
