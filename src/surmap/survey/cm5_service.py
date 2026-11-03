"""The CM5 service around the survey stream: `StreamDetections`, `StreamRegionPoints`, and the
`surmap.rpc` module that mounts `Cm5SurveyService` (`StreamSurvey` itself is `cm5_server`).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from surmap.detection.detector import decode_rgb
from surmap.detection.source import DetectionSource, DetectorExecution
from surmap.rpc.compose import Brick
from surmap.rpc.description import ServiceModule
from surmap.slam.base import SlamBackend
from surmap.slam.fake import InMemorySlamBackend
from surmap.slam.regions import (
    RegionPointSource,
    RegionQuery,
    RegionStatus,
    StreamRegionRouter,
    invalid_reason,
)
from surmap.survey.cm5_server import SlamFactory, stream_survey
from surmap.survey.moving_stream import _encoding_name, stream_moving_areas
from surmap.survey.object_points import InMemoryObjectPointSource, ObjectPointSource
from surmap.survey.stereo import FrameImage, StereoReconstructor
from surmap.survey.v1 import survey_pb2
from surmap.types import Vec3

# A region is streamed in chunks of at most this many points.
MAX_REGION_POINTS_PER_MESSAGE = 10_000

_REGION_STATUS = {
    RegionStatus.OK: survey_pb2.REGION_STATUS_OK,
    RegionStatus.FRAME_EXPIRED: survey_pb2.REGION_STATUS_FRAME_EXPIRED,
    RegionStatus.NO_POSE: survey_pb2.REGION_STATUS_NO_POSE,
    RegionStatus.INVALID_QUERY: survey_pb2.REGION_STATUS_INVALID_QUERY,
}


async def stream_detections(
    requests: AsyncIterable[survey_pb2.Cm5Request],
    source: DetectionSource | None,
) -> AsyncIterator[survey_pb2.DetectionResponse]:
    """Serve the detections stream: channel-0 frames in, detections out.

    A separate stream from `StreamSurvey` by design: the detector
    runs on its own cadence, so detection messages are never attached
    to survey output frames — each carries its `frame_id` (and
    `t_ns`) for the client to join against the frames it sent. One
    message is yielded per analyzed frame, including frames with no
    detections; a server with no detection source configured rejects
    the stream.
    """
    if source is None:
        raise ValueError("no detection source configured on this CM5 server")
    config_seen = False
    async for request in requests:
        if not config_seen:
            if request.WhichOneof("kind") != "config":
                raise ValueError("first request must be config")
            config_seen = True
            continue
        if request.WhichOneof("kind") != "frame":
            continue
        frame = request.frame
        if frame.channel != 0:
            continue
        rgb = decode_rgb(FrameImage(frame.width, frame.height, _encoding_name(frame), frame.data))
        tracked = await asyncio.to_thread(source.detect_tracked, frame.frame_id, rgb)
        yield survey_pb2.DetectionResponse(
            detections=survey_pb2.FrameDetections(
                frame_id=frame.frame_id,
                t_ns=frame.t_ns,
                detections=[
                    survey_pb2.ObjectDetection(
                        label=detection.label,
                        score=detection.score,
                        box=survey_pb2.Box(
                            x_min=detection.box_xyxy[0],
                            y_min=detection.box_xyxy[1],
                            x_max=detection.box_xyxy[2],
                            y_max=detection.box_xyxy[3],
                        ),
                        track_id=detection.track_id,
                    )
                    for detection in tracked
                ],
            )
        )
    if not config_seen:
        raise ValueError("first request must be config")


async def stream_region_points(
    requests: AsyncIterable[survey_pb2.RegionQuery],
    source: RegionPointSource | None,
    max_points_per_message: int = MAX_REGION_POINTS_PER_MESSAGE,
) -> AsyncIterator[survey_pb2.RegionPoints]:
    """Serve the region stream: SAM polygons in, dense map-frame points out.

    Each query is answered from its own frame only — nothing accumulates
    across frames or queries — in chunks whose last one is `final`. An
    invalid query is refused without asking for depth; a server with no
    region source configured rejects the stream.
    """
    if source is None:
        raise ValueError("no region source configured on this CM5 server")
    async for request in requests:
        query = RegionQuery(
            query_id=request.query_id,
            frame_id=request.frame_id,
            channel=request.channel,
            width=request.width,
            height=request.height,
            polygon=tuple((point.x, point.y) for point in request.polygon),
        )
        points: tuple[Vec3, ...] = ()
        if invalid_reason(query) is not None:
            status = RegionStatus.INVALID_QUERY
        else:
            result = await asyncio.to_thread(source.region_points, query)
            status, points = result.status, result.points
        step = max(1, max_points_per_message)
        chunks = [points[start : start + step] for start in range(0, len(points), step)] or [()]
        for index, chunk in enumerate(chunks):
            yield survey_pb2.RegionPoints(
                query_id=query.query_id,
                frame_id=query.frame_id,
                channel=query.channel,
                status=_REGION_STATUS[status],
                points=[survey_pb2.Point3(x=p.x, y=p.y, z=p.z) for p in chunk],
                final=index == len(chunks) - 1,
            )


def cm5_service_module(
    slam: SlamBackend | None = None,
    objects: ObjectPointSource | None = None,
    stereo: StereoReconstructor | None = None,
    detections: DetectionSource | None = None,
    regions: RegionPointSource | None = None,
    *,
    moving_areas: bool = True,
    slam_label: str = "inmemory",
    slam_factory: SlamFactory | None = None,
    stream_regions: bool = False,
) -> ServiceModule[Any]:
    """The `surmap.rpc` service module mounting `Cm5SurveyService`.

    With `stream_regions`, region queries no default `regions` source answers go to the
    backends `slam_factory` built for the survey streams open at the time.
    """
    router = StreamRegionRouter() if stream_regions else None
    object_points_enabled = objects is not None
    default_slam: SlamBackend = slam if slam is not None else InMemorySlamBackend()
    default_objects: ObjectPointSource = (
        objects if objects is not None else InMemoryObjectPointSource()
    )

    effective_regions: RegionPointSource | None = regions or router
    execution = detections if isinstance(detections, DetectorExecution) else None

    def bricks(_ctx: object) -> tuple[Brick, ...]:

        async def handler(
            requests: AsyncIterable[survey_pb2.Cm5Request], _ctx: Any
        ) -> AsyncIterator[survey_pb2.Cm5Response]:
            async for response in stream_survey(
                requests,
                default_slam,
                default_objects,
                stereo=stereo,
                slam_factory=slam_factory,
                stream_regions=router,
            ):
                yield response

        async def detections_handler(
            requests: AsyncIterable[survey_pb2.Cm5Request], _ctx: Any
        ) -> AsyncIterator[survey_pb2.DetectionResponse]:
            async for response in stream_detections(requests, detections):
                yield response

        async def moving_areas_handler(
            requests: AsyncIterable[survey_pb2.Cm5Request], _ctx: Any
        ) -> AsyncIterator[survey_pb2.MovingAreasResponse]:
            if not moving_areas:
                raise ValueError(
                    "moving areas are not enabled on this CM5 server "
                    "(start with --moving-areas to enable)"
                )
            async for response in stream_moving_areas(requests, stereo=stereo, slam=default_slam):
                yield response

        async def region_points_handler(
            requests: AsyncIterable[survey_pb2.RegionQuery], _ctx: Any
        ) -> AsyncIterator[survey_pb2.RegionPoints]:
            async for response in stream_region_points(requests, effective_regions):
                yield response

        async def capabilities_handler(
            _request: survey_pb2.CapabilitiesRequest, _ctx: Any
        ) -> survey_pb2.Capabilities:
            return survey_pb2.Capabilities(
                service="cm5",
                detections=detections is not None,
                object_points=object_points_enabled,
                moving_areas=moving_areas,
                region_points=effective_regions is not None,
                provider=execution.provider if execution is not None else "",
                device=execution.device if execution is not None else "",
                slam=slam_label,
            )

        return (
            Brick(
                methods={
                    "GetCapabilities": capabilities_handler,
                    "StreamSurvey": handler,
                    "StreamDetections": detections_handler,
                    "StreamMovingAreas": moving_areas_handler,
                    "StreamRegionPoints": region_points_handler,
                }
            ),
        )

    return ServiceModule(
        descriptor=survey_pb2.DESCRIPTOR.services_by_name["Cm5SurveyService"],
        bricks=bricks,
    )
