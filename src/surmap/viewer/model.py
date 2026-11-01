"""Viewer contracts. The semantic map file is read, never written back."""

from __future__ import annotations

from dataclasses import dataclass

from surmap.types import Vec3

SCHEMA = "surmap.semantic_map_snapshot.v1"


@dataclass(frozen=True)
class Origin:
    t_ns: int
    lat: float
    lon: float
    alt: float
    accuracy_m: float


@dataclass(frozen=True)
class Observation:
    t_ns: int
    xyz: Vec3


@dataclass(frozen=True)
class Track:
    """One landmark or moving track from a semantic map snapshot."""

    id: str
    xyz: Vec3
    lat: float | None
    lon: float | None
    alt: float | None
    label: str
    description: str
    model_id: str
    motion: str
    t_ns: int
    anchor_t_ns: int | None
    offset_ns: int | None
    observations: tuple[Observation, ...]
    mask_points: tuple[Vec3, ...] | None
    layer: str  # "landmarks" | "dynamic"


@dataclass(frozen=True)
class SemanticMapSnapshot:
    origin: Origin | None
    landmarks: tuple[Track, ...]
    dynamic: tuple[Track, ...]

    def tracks(self) -> tuple[Track, ...]:
        return self.landmarks + self.dynamic


def empty_snapshot() -> SemanticMapSnapshot:
    return SemanticMapSnapshot(origin=None, landmarks=(), dynamic=())


@dataclass(frozen=True)
class CameraModel:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int


@dataclass(frozen=True)
class Overlay:
    """One box on the camera frame, in image pixels."""

    xyxy: tuple[float, float, float, float]
    label: str
    motion: str
    track_id: str
    mask: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class PlacedTrack:
    """A track positioned on the replay clock."""

    track: Track
    xyz: Vec3
    trail: tuple[Vec3, ...]
    visible: bool


@dataclass(frozen=True)
class ViewerTick:
    index: int
    total: int
    t_ns: int
    jpeg: bytes
    width: int
    height: int
    drone: Vec3
    points: tuple[Vec3, ...]
    scene_points: int
    overlays: tuple[Overlay, ...]
    placed: tuple[PlacedTrack, ...]
    height_m: float
    gps_fix: bool
    pose_ok: bool
    hud: tuple[str, ...]


def hud_badges(
    *,
    mapping: bool,
    landmark_count: int,
    gps_fix: bool,
    pose_ok: bool,
) -> tuple[str, ...]:
    """Survey status for the camera HUD. Not a flight-controller mode."""
    badges = ["SURVEY"]
    if mapping:
        badges.append("MAPPING")
    badges.append(f"LANDMARKS {landmark_count}")
    if gps_fix:
        badges.append("GPS FIX")
    elif pose_ok:
        badges.append("POSE")
    else:
        badges.append("NO POSE")
    return tuple(badges)
