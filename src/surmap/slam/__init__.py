"""SLAM backends: RTAB-Map provides pose and static-scene points."""

from surmap.slam.base import FrameResult, SlamBackend
from surmap.slam.fake import InMemorySlamBackend
from surmap.slam.rtabmap import RtabmapBackend, RtabmapUnavailable

__all__ = [
    "FrameResult",
    "InMemorySlamBackend",
    "RtabmapBackend",
    "RtabmapUnavailable",
    "SlamBackend",
]
