"""CM5 ConnectRPC server: `Cm5SurveyService.StreamSurvey` (BIDI).

Frames and calibration in; incremental designated points and requested
video channels out. Points are streamed as they are spawned through the
`IncrementalPointEmitter` (n2) — a point still at a sent position is
never resent. RTAB-Map output is registration data only, never a control
signal (docs/architecture.md section 1).

Ordering within one arriving frame: the video echo for that frame is
yielded first, then (if it completed a pair) the point batches for the
pair — scene batch (designation 1) before object batches.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Any

from surmap.rpc.compose import Brick
from surmap.rpc.description import ServiceModule
from surmap.slam.base import SlamBackend
from surmap.slam.fake import InMemorySlamBackend
from surmap.survey.designations import object_designation, video_designation
from surmap.survey.object_points import InMemoryObjectPointSource, ObjectPointSource
from surmap.survey.points import IncrementalPointEmitter
from surmap.survey.v1 import survey_pb2
from surmap.types import StereoFramePair


@dataclass(frozen=True)
class Cm5Context:
    """Context carrying the SLAM backend and object-point source for a host."""

    slam: SlamBackend
    objects: ObjectPointSource


async def stream_survey(
    requests: AsyncIterable[survey_pb2.Cm5Request],
    slam: SlamBackend,
    objects: ObjectPointSource,
    emitter: IncrementalPointEmitter | None = None,
) -> AsyncIterator[survey_pb2.Cm5Response]:
    """Serve one CM5 survey stream: config first, then per-channel frames."""
    if emitter is None:
        emitter = IncrementalPointEmitter()
    config: survey_pb2.Cm5StreamConfig | None = None
    pending: dict[int, dict[int, survey_pb2.RawVideoFrame]] = {}
    async for request in requests:
        if config is None:
            if request.WhichOneof("kind") != "config":
                raise ValueError("first request must be config")
            config = request.config
            continue
        if request.WhichOneof("kind") != "frame":
            continue
        frame = request.frame
        if frame.channel in config.video_channels:
            yield survey_pb2.Cm5Response(
                video=survey_pb2.VideoFrameOut(
                    designation=video_designation(frame.channel), frame=frame
                )
            )
        channels = pending.setdefault(frame.frame_id, {})
        channels[frame.channel] = frame
        if 0 not in channels or 1 not in channels:
            continue
        t_ns = channels[0].t_ns
        pending.pop(frame.frame_id)
        # Refs are identifiers only; frame data stays in the messages.
        pair = StereoFramePair(
            frame_id=frame.frame_id,
            t_ns=t_ns,
            left_ref=f"frame-{frame.frame_id}-left",
            right_ref=f"frame-{frame.frame_id}-right",
            calibration_id=config.calibration.calibration_id,
        )
        result = slam.process_frame(pair)
        if result.pose is None:
            continue
        scene = emitter.emit(1, result.static_points)
        if scene:
            yield survey_pb2.Cm5Response(
                points=survey_pb2.PointBatch(
                    designation=1,
                    frame_id=result.frame_id,
                    t_ns=result.t_ns,
                    points=[survey_pb2.Point3(x=p.x, y=p.y, z=p.z) for p in scene],
                )
            )
        for obs in objects.points_for_pair(pair, result.pose):
            designation = object_designation(obs.track_id)
            fresh = emitter.emit(designation, obs.points)
            if fresh:
                yield survey_pb2.Cm5Response(
                    points=survey_pb2.PointBatch(
                        designation=designation,
                        frame_id=obs.frame_id,
                        t_ns=obs.t_ns,
                        points=[survey_pb2.Point3(x=p.x, y=p.y, z=p.z) for p in fresh],
                    )
                )
    if config is None:
        raise ValueError("first request must be config")


def cm5_service_module(
    slam: SlamBackend | None = None,
    objects: ObjectPointSource | None = None,
) -> ServiceModule[Any]:
    """The `surmap.rpc` service module mounting `Cm5SurveyService`."""
    default_slam: SlamBackend = slam if slam is not None else InMemorySlamBackend()
    default_objects: ObjectPointSource = (
        objects if objects is not None else InMemoryObjectPointSource()
    )

    def bricks(ctx: Any) -> tuple[Brick, ...]:
        effective_slam: SlamBackend = getattr(ctx, "slam", None) or default_slam
        effective_objects: ObjectPointSource = getattr(ctx, "objects", None) or default_objects

        async def handler(
            requests: AsyncIterable[survey_pb2.Cm5Request], _ctx: Any
        ) -> AsyncIterator[survey_pb2.Cm5Response]:
            async for response in stream_survey(requests, effective_slam, effective_objects):
                yield response

        return (Brick(methods={"StreamSurvey": handler}),)

    return ServiceModule(
        descriptor=survey_pb2.DESCRIPTOR.services_by_name["Cm5SurveyService"],
        bricks=bricks,
    )
