"""Vehicles in a scenario: the `vehicle` element's rules (the renderer's `vehicle.rs` and
`SceneManifest::validate_vehicles` apply the same) and the `street-traffic` preset."""

from __future__ import annotations

from collections.abc import Mapping

from surmap.simulation.manifest_checks import Manifest

VEHICLE_CLASSES = ("car", "bus", "truck", "train")


def validate_vehicle(element: Mapping[str, object]) -> None:
    """Raise `ScenarioInvalid` for a vehicle the renderer would refuse: an unknown `class`,
    `cars` on anything but a train, a `glb` that is not a relative glTF path, or a tree that is
    not valid for a body on the ground."""
    # TODO(pr-1): implement
    raise NotImplementedError("validate_vehicle")


def street_traffic(block: Manifest) -> Manifest:
    """The disaster block with traffic: cars and a truck on the avenue, a bus on the cross street,
    a parked car, and a six-carriage train on a rail line along the block's west edge."""
    # TODO(pr-1): implement
    raise NotImplementedError("street_traffic")
