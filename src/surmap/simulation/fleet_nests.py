"""Drone nests in a scenario: docking pads the agent places, each housing one to four of the
simulation's own drones, the rules that keep a pad where a drone could use it (the renderer's
`SceneManifest::validate_nests` applies the same, with the same messages), and the read API the
fleet builds on.

The pad is a `NEST_PAD_M` square, yawed about its centre. It may not overlap a building, a
collapsed building or a box with a collider unless it stands on that element's top (a rooftop
nest), nor a `water: true` surface; nest centres keep `NEST_SPACING_M` apart, and the drone ids
`<id>-d1 … <id>-dN` join the manifest's one id namespace.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from dataclasses import dataclass

from surmap.simulation.manifest_checks import Manifest, ScenarioInvalid, number, object_list
from surmap.simulation.water import water_surfaces

NEST_KIND = "drone_nest"
# The pad's side, m.
NEST_PAD_M = 2.4
# The least distance between two nest centres, m.
NEST_SPACING_M = 6.0
MAX_NESTS = 8
MAX_DRONES_PER_NEST = 4
# A pad centre lies within ±NEST_BOUND_M east and north of the origin.
NEST_BOUND_M = 500.0
# A pad's deck is at most NEST_MAX_UP_M above the ground (and never below it).
NEST_MAX_UP_M = 60.0
# Overlaps shallower than this are touching, not overlapping, m.
_TOUCH_M = 1e-4
# A pad standing this close to an element's top (below it) still counts as standing on it, m.
_ROOF_TOLERANCE_M = 0.05


@dataclass(frozen=True)
class Nest:
    """A nest as the fleet sees it: the pad's ENU centre at deck level, its heading and the ids
    of the drones it houses, in order."""

    id: str
    pad_enu: tuple[float, float, float]
    yaw_deg: float
    drone_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Footprint:
    """A yawed rectangle on the ground plane: centre, half-extents (east, north before yaw), yaw."""

    centre: tuple[float, float]
    half: tuple[float, float]
    yaw: float

    def axes(self) -> tuple[tuple[float, float], tuple[float, float]]:
        cos, sin = math.cos(self.yaw), math.sin(self.yaw)
        return (cos, sin), (-sin, cos)

    def reach(self, axis: tuple[float, float]) -> float:
        """The footprint's half-width along `axis`."""
        east, north = self.axes()
        return self.half[0] * abs(_dot(axis, east)) + self.half[1] * abs(_dot(axis, north))

    def overlaps(self, other: _Footprint) -> bool:
        """Separating-axis test: the two rectangles share area deeper than `_TOUCH_M`."""
        gap = (other.centre[0] - self.centre[0], other.centre[1] - self.centre[1])
        return all(
            abs(_dot(gap, axis)) < self.reach(axis) + other.reach(axis) - _TOUCH_M
            for axis in (*self.axes(), *other.axes())
        )


@dataclass(frozen=True)
class _Solid:
    """A thing a pad may not stand inside: its id, footprint and top (m above the ground)."""

    id: str
    footprint: _Footprint
    top: float


def _dot(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _numbers(value: object, count: int, what: str) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != count:
        raise ScenarioInvalid(f"{what} must be {count} numbers")
    return tuple(number(v, what) for v in value)


def _footprint(centre: tuple[float, ...], size: tuple[float, ...], yaw_deg: object) -> _Footprint:
    return _Footprint(
        (centre[0], centre[1]),
        (size[0] / 2.0, size[1] / 2.0),
        math.radians(number(yaw_deg, "yaw_deg")),
    )


def _solids(manifest: Mapping[str, object]) -> list[_Solid]:
    """Every building, collapsed building and collider box (water excluded) with its top."""
    found: list[_Solid] = []
    for element in object_list(manifest, "elements"):
        kind = element.get("kind")
        element_id = str(element.get("id"))
        if kind == "collapsed_building":
            at = _numbers(element.get("position_enu"), 3, f"{element_id} position_enu")
            size = _numbers(element.get("footprint_m"), 2, f"{element_id} footprint_m")
            slabs = number(element.get("slabs", 4), "slabs")
            thickness = number(element.get("slab_thickness_m", 0.30), "slab_thickness_m")
            found.append(
                _Solid(
                    element_id,
                    _footprint(at, size, element.get("yaw_deg", 0.0)),
                    at[2] + slabs * thickness,
                )
            )
        elif kind == "building" or (
            kind == "box" and element.get("collider") is True and element.get("water") is not True
        ):
            at = _numbers(element.get("position_enu"), 3, f"{element_id} position_enu")
            size = _numbers(element.get("size_m"), 3, f"{element_id} size_m")
            found.append(
                _Solid(
                    element_id, _footprint(at, size, element.get("yaw_deg", 0.0)), at[2] + size[2]
                )
            )
    return found


def _nest_elements(manifest: Mapping[str, object]) -> list[dict[str, object]]:
    return [e for e in object_list(manifest, "elements") if e.get("kind") == NEST_KIND]


def _drone_ids(nest_id: str, drones: int) -> tuple[str, ...]:
    return tuple(f"{nest_id}-d{n}" for n in range(1, drones + 1))


def _refused(nest_id: str, reason: str) -> ScenarioInvalid:
    return ScenarioInvalid(f"nest {nest_id}: {reason}")


def _drone_count(nest: Mapping[str, object]) -> int:
    nest_id = str(nest.get("id"))
    drones = nest.get("drones", 1)
    if isinstance(drones, bool) or not isinstance(drones, int):
        raise _refused(nest_id, f"drones must be 1 to {MAX_DRONES_PER_NEST}, got {drones!r}")
    if not 1 <= drones <= MAX_DRONES_PER_NEST:
        raise _refused(nest_id, f"drones must be 1 to {MAX_DRONES_PER_NEST}, got {drones}")
    return drones


def _validate_nest(
    nest: Mapping[str, object], solids: list[_Solid], waters: list[tuple[str, _Footprint]]
) -> tuple[float, float]:
    """One nest's own rules; returns its centre (east, north)."""
    nest_id = nest.get("id")
    if (
        not isinstance(nest_id, str)
        or not nest_id
        or not all(c.isascii() and (c.isalnum() or c == "-") for c in nest_id)
    ):
        raise _refused(str(nest_id), "id must be ASCII letters, digits and '-'")
    _drone_count(nest)
    east, north, up = _numbers(nest.get("position_enu"), 3, f"nest {nest_id} position_enu")
    if abs(east) > NEST_BOUND_M or abs(north) > NEST_BOUND_M:
        raise _refused(
            nest_id,
            f"pad centre ({east:g}, {north:g}) is outside ±{NEST_BOUND_M:g} m east and north",
        )
    if not 0.0 <= up <= NEST_MAX_UP_M:
        raise _refused(
            nest_id, f"pad deck at {up:g} m must be between 0 and {NEST_MAX_UP_M:g} m up"
        )
    pad = _footprint((east, north), (NEST_PAD_M, NEST_PAD_M), nest.get("yaw_deg", 0.0))
    for name, water in waters:
        if pad.overlaps(water):
            raise _refused(nest_id, f"pad overlaps water ({name})")
    for solid in solids:
        if up < solid.top - _ROOF_TOLERANCE_M and pad.overlaps(solid.footprint):
            raise _refused(
                nest_id,
                f"pad overlaps {solid.id}, which rises to {solid.top:g} m; "
                "a rooftop nest stands on its top",
            )
    return east, north


def validate_nests(manifest: Mapping[str, object]) -> None:
    """Raise `ScenarioInvalid` for a nest the renderer would refuse: an id outside ASCII letters,
    digits and `-`; a pad outside the bounds, over a solid footprint below its top or over water;
    `drones` outside 1–4; centres closer than 6 m; more than 8 nests; a drone id already taken.
    The reason names the nest and the rule."""
    nests = _nest_elements(manifest)
    if not nests:
        # A scene without nests has nothing to check.
        return
    if len(nests) > MAX_NESTS:
        raise ScenarioInvalid(f"a scenario holds at most {MAX_NESTS} nests, got {len(nests)}")
    solids = _solids(manifest)
    waters = [
        (surface.id, _Footprint(surface.centre, surface.half, surface.yaw))
        for surface in water_surfaces(manifest)
    ]
    centres: list[tuple[str, tuple[float, float]]] = []
    for nest in nests:
        centre = _validate_nest(nest, solids, waters)
        nest_id = str(nest.get("id"))
        for earlier_id, earlier in centres:
            distance = math.hypot(centre[0] - earlier[0], centre[1] - earlier[1])
            if distance < NEST_SPACING_M:
                raise _refused(
                    nest_id,
                    f"{distance:.1f} m from nest {earlier_id}, "
                    f"nests keep {NEST_SPACING_M:g} m apart",
                )
        centres.append((nest_id, centre))
    taken = set(other_ids(manifest))
    for nest in nests:
        for drone_id in _drone_ids(str(nest.get("id")), _drone_count(nest)):
            if drone_id in taken:
                raise ScenarioInvalid(f"duplicate id {drone_id!r}")
            taken.add(drone_id)


def other_ids(manifest: Mapping[str, object]) -> list[str]:
    """Every id the manifest declares itself (elements, models, fires, building fires), not the
    nests' derived drone ids."""
    ids: list[str] = []
    for key in ("elements", "models", "fires", "building_fires"):
        ids += [str(item.get("id")) for item in object_list(manifest, key)]
    return ids


def drone_ids_in(manifest: Mapping[str, object]) -> list[str]:
    """The drone ids of every nest in manifest order, `<id>-d1` … `<id>-dN`."""
    return [
        drone
        for nest in _nest_elements(manifest)
        for drone in _drone_ids(str(nest.get("id")), _drone_count(nest))
    ]


def nests_of(manifest: Mapping[str, object]) -> tuple[Nest, ...]:
    """The scenario's nests in manifest order, each with its defaults (`yaw_deg` 0, one drone)
    filled in and its drone ids named."""
    found: list[Nest] = []
    for nest in _nest_elements(manifest):
        nest_id = str(nest.get("id"))
        east, north, up = _numbers(nest.get("position_enu"), 3, f"nest {nest_id} position_enu")
        found.append(
            Nest(
                nest_id,
                (east, north, up),
                number(nest.get("yaw_deg", 0.0), "yaw_deg"),
                _drone_ids(nest_id, _drone_count(nest)),
            )
        )
    return tuple(found)


# The earthquake block's open ground south-west and north-east of the avenue, and the roof of its
# 16.5 m tall `building-6`.
_FLEET_NESTS: tuple[tuple[str, tuple[float, float, float], float, int], ...] = (
    ("nest-sw", (-40.0, -20.0, 0.0), 45.0, 2),
    ("nest-ne", (40.0, 100.0, 0.0), 225.0, 2),
    ("nest-roof", (78.55, 22.0, 16.5), 180.0, 1),
)


def earthquake_fleet(block: Manifest) -> Manifest:
    """`earthquake-block` with three drone nests: two two-drone nests on open ground, one
    single-drone nest on the roof of a standing building."""
    fleet: Manifest = copy.deepcopy(block)
    nests: list[dict[str, object]] = [
        {
            "kind": NEST_KIND,
            "id": nest_id,
            "position_enu": list(at),
            "yaw_deg": yaw_deg,
            "drones": drones,
        }
        for nest_id, at, yaw_deg, drones in _FLEET_NESTS
    ]
    fleet["elements"] = [*object_list(block, "elements"), *nests]
    validate_nests(fleet)
    return fleet
