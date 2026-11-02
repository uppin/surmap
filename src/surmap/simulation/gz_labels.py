"""Label plugins for the disaster-block models Gazebo can segment.

SurMap does not launch Gazebo. This module only edits SDF text. Class
ids match the bench exporter: 1 person, 2 car, 3 debris, 4 water.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CLASS_NAMES = {1: "person", 2: "car", 3: "debris", 4: "water"}

_MODEL = re.compile(
    r"(?P<indent>^[ \t]*)<model name=\"(?P<name>[^\"]+)\">(?P<body>.*?)^(?P=indent)</model>",
    re.MULTILINE | re.DOTALL,
)
_WORLD_PLUGIN = '    <plugin filename="gz-sim-label-system" name="gz::sim::systems::Label"/>\n'


@dataclass(frozen=True)
class LabelEdit:
    """SDF text after labelling, and each model that received a class."""

    text: str
    labelled: tuple[tuple[str, int], ...]


def label_for_model(name: str) -> int | None:
    """Class id for a disaster-block model, or None when it stays unlabelled."""
    if name.startswith("survivor_"):
        return 1
    if name.startswith("car_"):
        return 2
    if name.startswith(("rubble_", "plank_", "tire_", "burial")) or "debris" in name:
        return 3
    if "flood" in name or name.startswith("water"):
        return 4
    return None


def label_sdf(text: str) -> LabelEdit:
    """Insert label-system plugins. A second call does not duplicate them."""
    labelled: list[tuple[str, int]] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        class_id = label_for_model(name)
        body = match.group("body")
        indent = match.group("indent")
        if class_id is None:
            return match.group(0)
        labelled.append((name, class_id))
        if _already_labelled(body, class_id):
            return match.group(0)
        plugin = (
            f'{indent}  <plugin filename="gz-sim-label-system" '
            f'name="gz::sim::systems::Label">\n'
            f"{indent}    <label>{class_id}</label>\n"
            f"{indent}  </plugin>\n"
        )
        return f'{indent}<model name="{name}">{body}{plugin}{indent}</model>'

    updated = _MODEL.sub(replace, text)
    if _WORLD_PLUGIN.strip() not in updated:
        needle = '<world name="disaster_block">\n'
        if needle not in updated:
            raise ValueError("SDF has no disaster_block world")
        updated = updated.replace(needle, needle + _WORLD_PLUGIN, 1)
    return LabelEdit(updated, tuple(labelled))


def _already_labelled(body: str, class_id: int) -> bool:
    return f"<label>{class_id}</label>" in body and "gz-sim-label-system" in body
