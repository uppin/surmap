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

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Any

from surmap.detection.detector import decode_rgb
from surmap.detection.source import DetectionSource
from surmap.geometry import to_map_frame
from surmap.rpc.compose import Brick
from surmap.rpc.description import ServiceModule
from surmap.slam.base import FrameResult, SlamBackend
from surmap.slam.fake import InMemorySlamBackend
from surmap.survey.designations import object_designation, video_designation
from surmap.survey.object_points import InMemoryObjectPointSource, ObjectPointSource
from surmap.survey.points import IncrementalPointEmitter
from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from surmap.survey.v1 import survey_pb2
from surmap.types import StereoFramePair, Vec3


@dataclass(frozen=True)
class Cm5Context:
    """Context carrying the SLAM backend and object-point source for a host."""

    slam: SlamBackend
    objects: ObjectPointSource
    stereo: StereoReconstructor | None = None


def _encoding_name(frame: survey_pb2.RawVideoFrame) -> str:
    if frame.encoding == survey_pb2.FRAME_ENCODING_MJPEG:
        return "mjpeg"
    if frame.encoding == survey_pb2.FRAME_ENCODING_RAW_RGB:
        return "raw_rgb"
    return "unsupported"


def _point_responses(
    result: FrameResult,
    pair: StereoFramePair,
    scene_points: list[Vec3],
    objects: ObjectPointSource,
    emitter: IncrementalPointEmitter,
) -> list[survey_pb2.Cm5Response]:
    """Scene batch (designation 1) then object batches for one result."""
    responses: list[survey_pb2.Cm5Response] = []
    scene = emitter.emit(1, scene_points)
    if scene:
        responses.append(
            survey_pb2.Cm5Response(
                points=survey_pb2.PointBatch(
                    designation=1,
                    frame_id=result.frame_id,
                    t_ns=result.t_ns,
                    points=[survey_pb2.Point3(x=p.x, y=p.y, z=p.z) for p in scene],
                )
            )
        )
    for obs in objects.points_for_pair(pair, result.pose):
        designation = object_designation(obs.track_id)
        fresh = emitter.emit(designation, obs.points)
        if fresh:
            responses.append(
                survey_pb2.Cm5Response(
                    points=survey_pb2.PointBatch(
                        designation=designation,
                        frame_id=obs.frame_id,
                        t_ns=obs.t_ns,
                        points=[survey_pb2.Point3(x=p.x, y=p.y, z=p.z) for p in fresh],
                    )
                )
            )
    return responses


async def stream_survey(
    requests: AsyncIterable[survey_pb2.Cm5Request],
    slam: SlamBackend,
    objects: ObjectPointSource,
    emitter: IncrementalPointEmitter | None = None,
    stereo: StereoReconstructor | None = None,
) -> AsyncIterator[survey_pb2.Cm5Response]:
    """Serve one CM5 survey stream: config first, then per-channel frames."""
    if emitter is None:
        emitter = IncrementalPointEmitter()
    config: survey_pb2.Cm5StreamConfig | None = None
    pending: dict[int, dict[int, survey_pb2.RawVideoFrame]] = {}
    pairs: dict[int, StereoFramePair] = {}
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
        # Refs are identifiers; the bytes travel on the pair so
        # backends that consume images (e.g. the RTAB-Map sidecar)
        # can stage them without a second channel.
        pair = StereoFramePair(
            frame_id=frame.frame_id,
            t_ns=t_ns,
            left_ref=f"frame-{frame.frame_id}-left",
            right_ref=f"frame-{frame.frame_id}-right",
            calibration_id=config.calibration.calibration_id,
            left_data=channels[0].data,
            right_data=channels[1].data,
        )
        pairs[frame.frame_id] = pair
        result = slam.process_frame(pair)
        if result.pose is None:
            continue
        scene_points = list(result.static_points)
        if stereo is not None:
            calibration = config.calibration
            if calibration.focal_length_px > 0 and calibration.baseline_m > 0:
                rig = StereoRig(
                    fx=calibration.focal_length_px,
                    fy=calibration.focal_length_px,
                    cx=calibration.cx,
                    cy=calibration.cy,
                    baseline_m=calibration.baseline_m,
                )
                left_frame, right_frame = channels[0], channels[1]
                try:
                    camera_points = stereo.reconstruct(
                        FrameImage(
                            left_frame.width,
                            left_frame.height,
                            _encoding_name(left_frame),
                            left_frame.data,
                        ),
                        FrameImage(
                            right_frame.width,
                            right_frame.height,
                            _encoding_name(right_frame),
                            right_frame.data,
                        ),
                        rig,
                    )
                except ValueError:
                    camera_points = ()
                scene_points.extend(to_map_frame(point, result.pose) for point in camera_points)
        for response in _point_responses(result, pair, scene_points, objects, emitter):
            yield response
    if config is None:
        raise ValueError("first request must be config")
    # Batch backends (the RTAB-Map sidecar) only know their poses and
    # points once the whole stream is staged: flush them now, on this
    # still-open stream, so their scene/object batches arrive too.
    flush = getattr(slam, "flush", None)
    if callable(flush):
        for result in await asyncio.to_thread(flush):
            if result.pose is None:
                continue
            flushed_pair = pairs.get(result.frame_id)
            if flushed_pair is None:
                continue
            for response in _point_responses(
                result, flushed_pair, list(result.static_points), objects, emitter
            ):
                yield response


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


def cm5_service_module(
    slam: SlamBackend | None = None,
    objects: ObjectPointSource | None = None,
    stereo: StereoReconstructor | None = None,
    detections: DetectionSource | None = None,
) -> ServiceModule[Any]:
    """The `surmap.rpc` service module mounting `Cm5SurveyService`."""
    default_slam: SlamBackend = slam if slam is not None else InMemorySlamBackend()
    default_objects: ObjectPointSource = (
        objects if objects is not None else InMemoryObjectPointSource()
    )

    def bricks(ctx: Any) -> tuple[Brick, ...]:
        effective_slam: SlamBackend = getattr(ctx, "slam", None) or default_slam
        effective_objects: ObjectPointSource = getattr(ctx, "objects", None) or default_objects
        effective_stereo: StereoReconstructor | None = getattr(ctx, "stereo", None) or stereo

        async def handler(
            requests: AsyncIterable[survey_pb2.Cm5Request], _ctx: Any
        ) -> AsyncIterator[survey_pb2.Cm5Response]:
            async for response in stream_survey(
                requests, effective_slam, effective_objects, stereo=effective_stereo
            ):
                yield response

        effective_detections: DetectionSource | None = (
            getattr(ctx, "detections", None) or detections
        )

        async def detections_handler(
            requests: AsyncIterable[survey_pb2.Cm5Request], _ctx: Any
        ) -> AsyncIterator[survey_pb2.DetectionResponse]:
            async for response in stream_detections(requests, effective_detections):
                yield response

        return (Brick(methods={"StreamSurvey": handler, "StreamDetections": detections_handler}),)

    return ServiceModule(
        descriptor=survey_pb2.DESCRIPTOR.services_by_name["Cm5SurveyService"],
        bricks=bricks,
    )
