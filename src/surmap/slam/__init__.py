"""SLAM backends: RTAB-Map provides pose and static-scene points."""

from surmap.slam.base import FrameResult, SlamBackend
from surmap.slam.fake import InMemorySlamBackend
from surmap.slam.rtabmap import RtabmapBackend, RtabmapUnavailable
from surmap.slam.sidecar import PINNED_RTABMAP_IMAGE, SidecarError, SidecarRtabmapBackend

__all__ = [
    "PINNED_RTABMAP_IMAGE",
    "FrameResult",
    "InMemorySlamBackend",
    "RtabmapBackend",
    "RtabmapUnavailable",
    "SidecarError",
    "SidecarRtabmapBackend",
    "SlamBackend",
]
