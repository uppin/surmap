"""GPS-anchored semantic map snapshot.

The behaviour is not implemented yet. The types are the export contract
the tests pin down; ``build_snapshot`` and the file helpers raise until
that behaviour exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from surmap.types import GpsCheckpoint, Motion, ObjectTrack3D, Vec3

SNAPSHOT_SCHEMA = "surmap.semantic_map_snapshot.v1"


class MapOrigin:
    """Placeholder. Replaced when the snapshot behaviour is implemented."""

    t_ns: int
    lat: float
    lon: float
    alt: float
    accuracy_m: float


class MapObservation:
    """Placeholder. Replaced when the snapshot behaviour is implemented."""

    t_ns: int
    xyz: Vec3


class MapLandmark:
    """Placeholder. Replaced when the snapshot behaviour is implemented."""

    id: str
    xyz: Vec3
    lat: float | None
    lon: float | None
    alt: float | None
    label: str
    description: str
    model_id: str
    motion: Motion
    offset_ns: int | None
    anchor_t_ns: int | None
    t_ns: int
    observations: tuple[MapObservation, ...]
    mask_points: tuple[Vec3, ...] | None


class SemanticMapSnapshot:
    """Placeholder. Replaced when the snapshot behaviour is implemented."""

    schema: str
    origin: MapOrigin | None
    landmarks: tuple[MapLandmark, ...]
    dynamic: tuple[MapLandmark, ...]


def build_snapshot(
    tracks: Sequence[ObjectTrack3D],
    checkpoints: Sequence[GpsCheckpoint],
    *,
    descriptions: Mapping[int, str] | None = None,
    model_ids: Mapping[int, str] | None = None,
    mask_points: Mapping[int, Sequence[Vec3]] | None = None,
) -> SemanticMapSnapshot:
    raise NotImplementedError


def write_snapshot(snapshot: SemanticMapSnapshot, destination: Path) -> None:
    raise NotImplementedError


def read_snapshot(path: Path) -> SemanticMapSnapshot:
    raise NotImplementedError
