"""SLAM backends: RTAB-Map provides pose and static-scene points."""

from surmap.slam.base import FrameResult, SlamBackend
from surmap.slam.fake import InMemorySlamBackend
from surmap.slam.rtabmap import RtabmapBackend, RtabmapUnavailable
from surmap.slam.sidecar import (
    PINNED_RTABMAP_IMAGE,
    SHARED_CONTAINER_ENV,
    SidecarError,
    SidecarRtabmapBackend,
)
from surmap.slam.stream_protocol import GraphUpdate, KeyframeUpdate, MapUpdate, OdomUpdate
from surmap.slam.streaming import StreamingRtabmapBackend

__all__ = [
    "PINNED_RTABMAP_IMAGE",
    "SHARED_CONTAINER_ENV",
    "FrameResult",
    "GraphUpdate",
    "InMemorySlamBackend",
    "KeyframeUpdate",
    "MapUpdate",
    "OdomUpdate",
    "RtabmapBackend",
    "RtabmapUnavailable",
    "SidecarError",
    "SidecarRtabmapBackend",
    "SlamBackend",
    "StreamingRtabmapBackend",
]
