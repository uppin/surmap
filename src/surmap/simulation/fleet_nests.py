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

from collections.abc import Mapping
from dataclasses import dataclass

from surmap.simulation.manifest_checks import object_list

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


@dataclass(frozen=True)
class Nest:
    """A nest as the fleet sees it: the pad's ENU centre at deck level, its heading and the ids
    of the drones it houses, in order."""

    id: str
    pad_enu: tuple[float, float, float]
    yaw_deg: float
    drone_ids: tuple[str, ...]


def _has_nests(manifest: Mapping[str, object]) -> bool:
    return any(element.get("kind") == NEST_KIND for element in object_list(manifest, "elements"))


def validate_nests(manifest: Mapping[str, object]) -> None:
    """Raise `ScenarioInvalid` for a nest the renderer would refuse: an id outside ASCII letters,
    digits and `-`; a pad outside the bounds, over a solid footprint below its top or over water;
    `drones` outside 1–4; centres closer than 6 m; more than 8 nests; a drone id already taken.
    The reason names the nest and the rule."""
    if not _has_nests(manifest):
        # A scene without nests has nothing to check.
        return
    # TODO(pr-1): implement
    raise NotImplementedError("pr-1: implement")


def nests_of(manifest: Mapping[str, object]) -> tuple[Nest, ...]:
    """The scenario's nests in manifest order, each with its defaults (`yaw_deg` 0, one drone)
    filled in and its drone ids named."""
    # TODO(pr-1): implement
    raise NotImplementedError("pr-1: implement")
