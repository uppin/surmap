"""Boats and ships in a scenario: water surfaces (`box` elements with `water: true`), the rules that
keep a vessel on them (the renderer's `SceneManifest::validate_vessels` applies the same), and the
`flood-rescue` preset."""

from __future__ import annotations

from collections.abc import Mapping

from surmap.simulation.manifest_checks import Manifest

VESSEL_CLASSES = ("boat", "ship")


def validate_vessels(manifest: Mapping[str, object]) -> None:
    """Raise `ScenarioInvalid` when a boat or ship starts off water, steers (`move_to`,
    `follow_path`) to a point off water, or has `wander` / `flee_from_fire` in its tree; or when a
    road or rail vehicle starts on water. The reason names the vehicle and the point."""
    # TODO(pr-3): implement
    raise NotImplementedError("validate_vessels")


def flood_rescue(flood_street: Manifest) -> Manifest:
    """`flood-street` with 0.6 m of floodwater over the avenue, two rescue boats shuttling its
    length, and a survivor waiting at its north end."""
    # TODO(pr-3): implement
    raise NotImplementedError("flood_rescue")
