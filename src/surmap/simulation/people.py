"""People in a scenario: the `person` element's pose, height and rig override (the renderer's
`SceneManifest::validate_people` applies the same rules) and the `earthquake-survivors` preset."""

from __future__ import annotations

from collections.abc import Mapping

from surmap.simulation.manifest_checks import Manifest

POSES = ("standing", "lying", "sitting", "waving")
HEIGHT_RANGE_M = (0.9, 2.2)


def validate_person_look(element: Mapping[str, object]) -> None:
    """Raise `ScenarioInvalid` for a person the renderer would refuse: an unknown `pose`, a
    `height_m` outside `HEIGHT_RANGE_M`, a `yaw_deg` that is not a number, or a `glb` that is not
    a relative glTF path."""
    # TODO(pr-2): implement
    raise NotImplementedError("validate_person_look")


def earthquake_survivors(block: Manifest) -> Manifest:
    """The disaster block the morning after: a survivor lying by `collapsed-0`, one sitting on
    the rubble of `collapsed-2`, one waving from `collapsed-3`, and two rescuers walking between
    them."""
    # TODO(pr-2): implement
    raise NotImplementedError("earthquake_survivors")
