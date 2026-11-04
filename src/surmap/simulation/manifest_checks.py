"""What every scenario-manifest rule shares: the refusal, the manifest type and two value checks.

`scenario_manifest` (the scene) and `behaviour_tree` (its behaviour trees) both raise
`ScenarioInvalid`; keeping it here lets the manifest validate its trees without an import cycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath

Manifest = dict[str, object]


class ScenarioInvalid(ValueError):
    """A manifest the renderer would refuse, and why."""


def object_list(manifest: Mapping[str, object], key: str) -> list[dict[str, object]]:
    value = manifest.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ScenarioInvalid(f"{key} must be a list of objects")
    return [{str(k): v for k, v in item.items()} for item in value]


def number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioInvalid(f"{what} must be a number")
    return float(value)


def is_relative_path(path: str) -> bool:
    """A path that stays inside its assets directory: not absolute, no `..`, no empty segment."""
    pure = PurePosixPath(path)
    return not pure.is_absolute() and ".." not in pure.parts and "" not in path.split("/")
