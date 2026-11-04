"""People in a scenario: the `person` element's pose, height, facing and rig override (the
renderer's `SceneManifest::validate_people` applies the same rules) and the `earthquake-survivors`
preset."""

from __future__ import annotations

import copy
from collections.abc import Mapping

from surmap.simulation.manifest_checks import (
    Manifest,
    ScenarioInvalid,
    is_relative_path,
    number,
    object_list,
)

POSES = ("standing", "lying", "sitting", "waving")
HEIGHT_RANGE_M = (0.9, 2.2)
RESCUE_SPEED_M_S = 1.4


def validate_person_look(element: Mapping[str, object]) -> None:
    """Raise `ScenarioInvalid` for a person the renderer would refuse: an unknown `pose`, a
    `height_m` outside `HEIGHT_RANGE_M`, a `yaw_deg` that is not a number, or a `glb` that is not
    a relative glTF path. The reason names the person and the field."""
    person = element.get("id")
    pose = element.get("pose", "standing")
    if pose not in POSES:
        raise ScenarioInvalid(f"person {person}: pose {pose!r} must be one of {POSES}")
    if element.get("height_m") is not None:
        height = number(element["height_m"], f"person {person}: height_m")
        low, high = HEIGHT_RANGE_M
        if not low <= height <= high:
            raise ScenarioInvalid(f"person {person}: height_m {height:g} must be {low}–{high} m")
    if element.get("yaw_deg") is not None:
        number(element["yaw_deg"], f"person {person}: yaw_deg")
    glb = element.get("glb")
    if glb is not None:
        if not (isinstance(glb, str) and is_relative_path(glb) and glb.endswith((".glb", ".gltf"))):
            raise ScenarioInvalid(
                f"person {person}: glb {glb!r} must be a relative .glb or .gltf path"
            )


def _person(
    person_id: str,
    position: tuple[float, float, float],
    coat: str,
    **fields: object,
) -> dict[str, object]:
    return {
        "kind": "person",
        "id": person_id,
        "position_enu": list(position),
        "coat": coat,
        "skin": "skin",
        **fields,
    }


def _patrol(there: tuple[float, float], back: tuple[float, float]) -> dict[str, object]:
    """Walk to `there` and back to `back`, for as long as the scenario runs."""
    legs: list[object] = [
        {"node": "follow_path", "id": name, "enu": [list(point)], "speed_m_s": RESCUE_SPEED_M_S}
        for name, point in (("there", there), ("back", back))
    ]
    return {"node": "repeat", "child": {"node": "sequence", "id": "patrol", "children": legs}}


def earthquake_survivors(block: Manifest) -> Manifest:
    """The disaster block the morning after. The shipped block's seven standing survivors give way
    to five people: a survivor lying by `collapsed-0`, one sitting on the rubble of `collapsed-2`,
    one waving from `collapsed-3`, and two rescuers walking between them."""
    scenario: Manifest = copy.deepcopy(block)
    kept = [e for e in object_list(block, "elements") if e.get("kind") != "person"]
    people: list[dict[str, object]] = [
        _person(
            "survivor-lying",
            (-3.0, 29.0, 0.0),
            "coat_yellow",
            pose="lying",
            yaw_deg=20.0,
            height_m=1.75,
        ),
        _person(
            "survivor-sitting",
            (18.0, 52.0, 1.0),
            "coat_yellow",
            pose="sitting",
            yaw_deg=180.0,
            height_m=1.7,
        ),
        _person(
            "survivor-waving",
            (9.0, 83.0, 0.0),
            "coat_yellow",
            pose="waving",
            yaw_deg=-60.0,
            height_m=1.7,
        ),
        {
            **_person("rescuer-1", (-6.0, 36.0, 0.0), "coat_orange"),
            "behaviour": _patrol((12.0, 44.0), (-6.0, 36.0)),
        },
        {
            **_person("rescuer-2", (10.0, 66.0, 0.0), "coat_orange"),
            "behaviour": _patrol((12.0, 80.0), (10.0, 66.0)),
        },
    ]
    scenario["elements"] = [*kept, *people]
    return scenario
