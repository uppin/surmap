"""Snippet registry and oracle converters (design section 6.1/6.2).

TODO(n2): implemented by pr-2-moving-snippets' Green row.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SnippetSpec:
    """One recorded snippet fixture (manifest entry)."""

    snippet_id: str
    scene: str  # traffic | fire | swarm | stereo
    source_url: str
    license: str


@dataclass(frozen=True)
class OracleBox:
    """One annotated mover box on one frame."""

    frame_index: int
    track_id: int
    label: str
    left: float
    top: float
    width: float
    height: float


def snippet_specs() -> tuple[SnippetSpec, ...]:
    """All registered snippets (traffic, fire, swarm, KITTI stereo)."""
    raise NotImplementedError("TODO(n2): snippet registry")


def parse_visdrone_mot(text: str) -> tuple[OracleBox, ...]:
    """Parse VisDrone MOT annotations into oracle boxes."""
    raise NotImplementedError("TODO(n2): VisDrone MOT converter")


def parse_purdue_refined_gt(text: str) -> tuple[OracleBox, ...]:
    """Parse Purdue UAV_Dataset refined_gt annotations into oracle boxes."""
    raise NotImplementedError("TODO(n2): Purdue refined_gt converter")


def kitti_sensor_yaml(calib_text: str, width: int, height: int) -> str:
    """Derive a EuRoC cam sensor.yaml from a KITTI tracking calib file."""
    raise NotImplementedError("TODO(n2): KITTI calib -> sensor.yaml")
