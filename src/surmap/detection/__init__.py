"""On-board object detection + tracking (Coral Edge TPU component)."""

from surmap.detection.detector import CoralDetector, DetectorUnavailable
from surmap.detection.profiles import DEFAULT_PROFILE, MODEL_PROFILES, ModelProfile
from surmap.detection.source import (
    CoralDetectionSource,
    CoralObjectPointSource,
    DetectionSource,
)
from surmap.detection.tracker import IouTracker, TrackedDetection

__all__ = [
    "DEFAULT_PROFILE",
    "MODEL_PROFILES",
    "CoralDetectionSource",
    "CoralDetector",
    "CoralObjectPointSource",
    "DetectionSource",
    "DetectorUnavailable",
    "IouTracker",
    "ModelProfile",
    "TrackedDetection",
]
