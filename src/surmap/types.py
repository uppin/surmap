"""Data contracts from docs/architecture.md (section 6).

Plain dataclasses, no third-party dependencies. Image and mask payloads
are referenced, never embedded in metadata records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import sqrt


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def norm(self) -> float:
        return sqrt(self.x**2 + self.y**2 + self.z**2)


@dataclass(frozen=True)
class Pose:
    """Camera pose in the map frame: position plus quaternion (x, y, z, w)."""

    position: Vec3
    orientation_xyzw: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)


@dataclass(frozen=True)
class StereoFramePair:
    frame_id: int
    t_ns: int
    left_ref: str
    right_ref: str
    calibration_id: str


@dataclass(frozen=True)
class GpsCheckpoint:
    t_ns: int
    lat: float
    lon: float
    alt: float
    accuracy_m: float


@dataclass(frozen=True)
class Detection:
    frame_id: int
    box_xyxy: tuple[float, float, float, float]
    label: str
    score: float
    detector_model_id: str


@dataclass
class Track:
    track_id: int
    label: str
    detections: list[Detection] = field(default_factory=list)

    @property
    def first_seen_frame(self) -> int | None:
        return self.detections[0].frame_id if self.detections else None

    @property
    def last_seen_frame(self) -> int | None:
        return self.detections[-1].frame_id if self.detections else None


class Motion(Enum):
    STATIC = "static"
    MOVING = "moving"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ObjectPoints:
    """One observation of one tracked object, points already in map frame."""

    track_id: int
    frame_id: int
    t_ns: int
    points: tuple[Vec3, ...]
    centroid: Vec3


@dataclass
class ObjectTrack3D:
    track_id: int
    label: str
    observations: list[ObjectPoints] = field(default_factory=list)
    motion: Motion = Motion.UNKNOWN
