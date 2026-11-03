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
from collections.abc import AsyncIterable, AsyncIterator, Callable

import numpy as np

from surmap.geometry import to_map_frame
from surmap.slam.base import FrameResult, SlamBackend
from surmap.slam.capabilities import (
    FlushableBackend,
    KeyframeSource,
    MapSnapshotSource,
    OdometrySource,
    RectificationSource,
)
from surmap.slam.regions import (
    RegionPointSource,
    StreamRegionRouter,
)
from surmap.slam.stream_protocol import KeyframeUpdate, OdomUpdate, Rectification
from surmap.survey.designations import object_designation, video_designation
from surmap.survey.gps import PendingFixes, PoseTimeline
from surmap.survey.moving_stream import _encoding_name as _encoding_name
from surmap.survey.moving_stream import stream_moving_areas as stream_moving_areas
from surmap.survey.object_points import ObjectPointSource
from surmap.survey.offload import forget_backend, run_blocking
from surmap.survey.points import IncrementalPointEmitter
from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from surmap.survey.v1 import survey_pb2
from surmap.types import StereoFramePair, Vec3

# A survey stream with no request for this long still drains what a live backend produced since
# (odometry, keyframes, the GPS anchors waiting for them).
IDLE_DRAIN_S = 0.1


async def _with_idle_ticks(
    requests: AsyncIterable[survey_pb2.Cm5Request], idle_s: float
) -> AsyncIterator[survey_pb2.Cm5Request | None]:
    """`requests`, with a `None` whenever `idle_s` passes without one. The pending read is kept
    across ticks, never cancelled."""
    iterator = aiter(requests)
    pending: asyncio.Future[survey_pb2.Cm5Request] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(anext(iterator))
            done, _ = await asyncio.wait({pending}, timeout=idle_s)
            if not done:
                yield None
                continue
            try:
                request = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            yield request
    finally:
        if pending is not None and not pending.done():
            pending.cancel()


# The local streaming backend stores at most this many points per
# keyframe; the survey emits no more per keyframe either.
MAX_EMITTED_POINTS_PER_KEYFRAME = 1000


def _placed_keyframe_points(update: KeyframeUpdate) -> list[Vec3]:
    """A keyframe's local points in the map frame, evenly capped.

    Placement is vectorized: rotating thousands of points one by one
    in Python costs more than the RTAB-Map step that produced them.
    """
    points = update.points_local
    if len(points) > MAX_EMITTED_POINTS_PER_KEYFRAME:
        step = len(points) / MAX_EMITTED_POINTS_PER_KEYFRAME
        points = tuple(points[int(i * step)] for i in range(MAX_EMITTED_POINTS_PER_KEYFRAME))
    if not points:
        return []
    array = np.array([(p.x, p.y, p.z) for p in points], dtype=np.float64)
    x, y, z, w = update.pose.orientation_xyzw
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    origin = update.pose.position
    placed = array @ rotation.T + np.array([origin.x, origin.y, origin.z])
    return [Vec3(float(px), float(py), float(pz)) for px, py, pz in placed.tolist()]


def _odom_response(
    update: OdomUpdate, rectification: Rectification | None
) -> survey_pb2.Cm5Response:
    """One frame's odometry as a survey response (see OdomUpdateOut)."""
    message = survey_pb2.OdomUpdateOut(
        frame_id=update.frame_id,
        t_ns=update.t_ns,
        keypoints=[
            survey_pb2.TrackedKeypoint(word_id=k.word_id, u=k.u, v=k.v, depth=k.depth)
            for k in update.keypoints
        ],
    )
    if update.pose is not None:
        message.position.CopyFrom(
            survey_pb2.Point3(
                x=update.pose.position.x, y=update.pose.position.y, z=update.pose.position.z
            )
        )
        message.orientation_xyzw.extend(update.pose.orientation_xyzw)
    if update.map_pose is not None:
        message.map_position.CopyFrom(
            survey_pb2.Point3(
                x=update.map_pose.position.x,
                y=update.map_pose.position.y,
                z=update.map_pose.position.z,
            )
        )
        message.map_orientation_xyzw.extend(update.map_pose.orientation_xyzw)
    if rectification is not None:
        message.rectification.CopyFrom(
            survey_pb2.RectificationOut(
                rotation=rectification.rotation,
                rectified=rectification.rectified,
                raw=rectification.raw,
                distortion=rectification.distortion,
            )
        )
    return survey_pb2.Cm5Response(odom=message)


def _point_responses(
    result: FrameResult,
    pair: StereoFramePair,
    scene_points: list[Vec3],
    objects: ObjectPointSource,
    emitter: IncrementalPointEmitter,
    rig: StereoRig | None = None,
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
    for obs in objects.points_for_pair(pair, result.pose, rig):
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


SlamFactory = Callable[[survey_pb2.Cm5StreamConfig], SlamBackend | None]
"""Builds one survey stream's own SLAM backend from its config, or
None to serve the stream on the server's configured backend. A built
backend is owned by the stream: it is closed when the stream ends,
so no map or odometry leaks into the next stream."""


async def stream_survey(
    requests: AsyncIterable[survey_pb2.Cm5Request],
    slam: SlamBackend,
    objects: ObjectPointSource,
    emitter: IncrementalPointEmitter | None = None,
    stereo: StereoReconstructor | None = None,
    slam_factory: SlamFactory | None = None,
    stream_regions: StreamRegionRouter | None = None,
) -> AsyncIterator[survey_pb2.Cm5Response]:
    """Serve one CM5 survey stream: config first, then per-channel frames and GPS fixes.

    A backend `slam_factory` builds for this stream answers `stream_regions` while it is open.
    """
    owned: list[SlamBackend] = []
    try:
        async for response in _stream_survey(
            requests, slam, objects, emitter, stereo, slam_factory, owned, stream_regions
        ):
            yield response
    finally:
        if owned:
            if stream_regions is not None and isinstance(owned[0], RegionPointSource):
                stream_regions.close(owned[0])
            owned[0].close()
            forget_backend(owned[0])


async def _stream_survey(
    requests: AsyncIterable[survey_pb2.Cm5Request],
    slam: SlamBackend,
    objects: ObjectPointSource,
    emitter: IncrementalPointEmitter | None = None,
    stereo: StereoReconstructor | None = None,
    slam_factory: SlamFactory | None = None,
    owned: list[SlamBackend] | None = None,
    stream_regions: StreamRegionRouter | None = None,
) -> AsyncIterator[survey_pb2.Cm5Response]:
    if emitter is None:
        emitter = IncrementalPointEmitter()
    config: survey_pb2.Cm5StreamConfig | None = None
    pending: dict[int, dict[int, survey_pb2.RawVideoFrame]] = {}
    pairs: dict[int, StereoFramePair] = {}
    odom_pending: set[int] = set()
    rectification_sent = False
    timeline = PoseTimeline()
    fixes = PendingFixes()

    def drain_odom() -> list[survey_pb2.Cm5Response]:
        """Odometry responses for pending frames whose odometry landed."""
        nonlocal rectification_sent
        if not isinstance(slam, OdometrySource):
            return []
        responses: list[survey_pb2.Cm5Response] = []
        for frame_id in sorted(odom_pending):
            update = slam.frame_odometry(frame_id)
            if update is None:
                continue
            pair = pairs.get(frame_id)
            if pair is None or update.t_ns != pair.t_ns:
                # Odometry from an earlier stream on a shared backend
                # (same frame_id, another run's timestamps): not ours.
                odom_pending.discard(frame_id)
                continue
            odom_pending.discard(frame_id)
            posed = update.map_pose or update.pose
            if posed is not None:
                timeline.add(frame_id, update.t_ns, posed.position)
            rectification: Rectification | None = None
            if not rectification_sent and isinstance(slam, RectificationSource):
                candidate = slam.rectification
                if candidate is not None:
                    rectification, rectification_sent = candidate, True
            responses.append(_odom_response(update, rectification))
        return responses

    def drain_keyframes() -> list[survey_pb2.Cm5Response]:
        """Scene batches for keyframes that landed. New keyframes only: placing their local
        points costs O(new), unlike re-scanning the whole map snapshot per pair (which grows
        with the cloud and throttles the stream)."""
        if not isinstance(slam, KeyframeSource):
            return []
        responses: list[survey_pb2.Cm5Response] = []
        for update in slam.poll_updates():
            if not isinstance(update, KeyframeUpdate):
                continue
            fresh = emitter.emit(1, _placed_keyframe_points(update))
            if fresh:
                responses.append(
                    survey_pb2.Cm5Response(
                        points=survey_pb2.PointBatch(
                            designation=1,
                            frame_id=update.frame_id,
                            t_ns=update.t_ns,
                            points=[survey_pb2.Point3(x=p.x, y=p.y, z=p.z) for p in fresh],
                        )
                    )
                )
        return responses

    async for request in _with_idle_ticks(requests, IDLE_DRAIN_S):
        if request is None:
            # The sender is idle: stream what a live backend produced meanwhile.
            if config is not None:
                for response in [*drain_odom(), *drain_keyframes(), *fixes.resolve(timeline)]:
                    yield response
            continue
        if config is None:
            if request.WhichOneof("kind") != "config":
                raise ValueError("first request must be config")
            config = request.config
            if slam_factory is not None:
                built = slam_factory(config)
                if built is not None:
                    slam = built
                    if owned is not None:
                        owned.append(built)
                    if stream_regions is not None and isinstance(built, RegionPointSource):
                        stream_regions.open(built)
            # Whatever the backend already maps predates this stream:
            # mark it sent so only this stream's own points go out,
            # and drain keyframe updates queued by earlier streams.
            if isinstance(slam, MapSnapshotSource):
                emitter.emit(1, slam.map_snapshot())
            if isinstance(slam, KeyframeSource):
                slam.poll_updates()
            continue
        if request.WhichOneof("kind") == "gps":
            fixes.add(request.gps)
            for response in fixes.resolve(timeline):
                yield response
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
        odom_pending.add(frame.frame_id)
        result = await run_blocking(slam, slam.process_frame, pair)
        # Live-backend extras the pair result cannot carry (a streaming
        # backend's result has no pose yet): odometry that has landed
        # since (pose + tracked keypoints for the video overlay) and
        # the map snapshot growing behind it.
        for response in [*drain_odom(), *drain_keyframes()]:
            yield response
        if result.pose is not None:
            timeline.add(pair.frame_id, pair.t_ns, result.pose.position)
        for response in fixes.resolve(timeline):
            yield response
        if result.pose is None:
            continue
        scene_points = list(result.static_points)
        calibration = config.calibration
        rig: StereoRig | None = None
        if calibration.focal_length_px > 0 and calibration.baseline_m > 0:
            rig = StereoRig(
                fx=calibration.focal_length_px,
                fy=calibration.focal_length_px,
                cx=calibration.cx,
                cy=calibration.cy,
                baseline_m=calibration.baseline_m,
            )
        if stereo is not None and rig is not None:
            left_frame, right_frame = channels[0], channels[1]
            try:
                camera_points = await asyncio.to_thread(
                    stereo.reconstruct,
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
        for response in await run_blocking(
            objects, _point_responses, result, pair, scene_points, objects, emitter, rig
        ):
            yield response
    if config is None:
        raise ValueError("first request must be config")
    # Batch backends (the RTAB-Map sidecar) only know their poses and
    # points once the whole stream is staged: flush them now, on this
    # still-open stream, so their scene/object batches arrive too.
    if isinstance(slam, FlushableBackend):
        calibration = config.calibration
        flush_rig: StereoRig | None = None
        if calibration.focal_length_px > 0 and calibration.baseline_m > 0:
            flush_rig = StereoRig(
                fx=calibration.focal_length_px,
                fy=calibration.focal_length_px,
                cx=calibration.cx,
                cy=calibration.cy,
                baseline_m=calibration.baseline_m,
            )
        for result in await run_blocking(slam, slam.flush):
            if result.pose is None:
                continue
            flushed_pair = pairs.get(result.frame_id)
            if flushed_pair is None:
                continue
            for response in await run_blocking(
                objects,
                _point_responses,
                result,
                flushed_pair,
                list(result.static_points),
                objects,
                emitter,
                flush_rig,
            ):
                yield response
        for response in drain_odom():
            yield response
    # A fix still waiting for a later pose is answered with what the stream had.
    for response in fixes.resolve(timeline, final=True):
        yield response
