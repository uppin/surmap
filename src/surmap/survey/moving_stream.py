"""CM5 moving-areas stream: `Cm5SurveyService.StreamMovingAreas` (BIDI).

Split out of `cm5_server` when the assembled handler (verdicts,
keypoints, flush-time map-frame snapshots) outgrew the survey
server's file. Behaviour is unchanged.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator

from surmap.geometry import to_map_frame
from surmap.moving.config import MovingConfig
from surmap.slam.base import SlamBackend
from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from surmap.survey.v1 import survey_pb2
from surmap.types import Pose, StereoFramePair, Vec3


def _encoding_name(frame: survey_pb2.RawVideoFrame) -> str:
    if frame.encoding == survey_pb2.FRAME_ENCODING_MJPEG:
        return "mjpeg"
    if frame.encoding == survey_pb2.FRAME_ENCODING_RAW_RGB:
        return "raw_rgb"
    return "unsupported"


_VERDICT_PROTO = {
    "unknown": survey_pb2.MOVING_VERDICT_UNKNOWN,
    "rigid_mover": survey_pb2.MOVING_VERDICT_RIGID_MOVER,
    "oscillating": survey_pb2.MOVING_VERDICT_OSCILLATING,
}


def _polygon_area(polygon: tuple[tuple[float, float], ...]) -> float:
    area = 0.0
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


async def stream_moving_areas(
    requests: AsyncIterable[survey_pb2.Cm5Request],
    stereo: StereoReconstructor | None = None,
    moving_config: MovingConfig | None = None,
    slam: SlamBackend | None = None,
) -> AsyncIterator[survey_pb2.MovingAreasResponse]:
    """Serve the moving-areas stream: stereo pairs in, areas + snapshots out.

    A separate stream by design (it lags the survey/detections
    streams and joins by `frame_id`). Areas are published live
    with terminal, versioned verdicts; graduated tracks buffer
    keypoint observations and, when a SLAM backend is present,
    flush-time snapshots are placed in the map frame once the
    backend flushes (design steps 6-7). The first analyzed frame
    seeds the static layer (cold-start bootstrap); later frames
    difference against it, and agreeing points extend it only
    through the layer's dwell gate (`observe_frame`).
    """
    from surmap.geometry import centroid as _centroid
    from surmap.moving.areas import AreaTracker, areas_from_clusters
    from surmap.moving.buffer import Observation, ObservationBuffer
    from surmap.moving.classify import TrackMotionStats, Verdict, VerdictMachine
    from surmap.moving.differencing import StaticLayer
    from surmap.moving.keypoints import select_keypoints
    from surmap.moving.placement import (
        KeyframePose,
        build_snapshot,
        distribute_correction,
        object_track_id,
    )

    config: survey_pb2.Cm5StreamConfig | None = None
    layer: StaticLayer | None = None
    tracker: AreaTracker | None = None
    verdicts: VerdictMachine | None = None
    motion_stats = TrackMotionStats()
    observations = ObservationBuffer()
    buffered_frame_ids: dict[int, list[int]] = {}
    previous_centroids: dict[int, tuple[int, Vec3]] = {}
    final_verdicts: dict[int, Verdict] = {}
    pending: dict[int, dict[int, survey_pb2.RawVideoFrame]] = {}
    async for request in requests:
        if config is None:
            if request.WhichOneof("kind") != "config":
                raise ValueError("first request must be config")
            config = request.config
            base = moving_config or MovingConfig()
            calibration = config.calibration
            if calibration.focal_length_px > 0 and calibration.baseline_m > 0:
                base = MovingConfig(
                    **{
                        **base.__dict__,
                        "focal_px": calibration.focal_length_px,
                        "baseline_m": calibration.baseline_m,
                    }
                )
            layer = StaticLayer(base)
            tracker = AreaTracker(base)
            verdicts = VerdictMachine(base)
            continue
        if request.WhichOneof("kind") != "frame":
            continue
        frame = request.frame
        channels = pending.setdefault(frame.frame_id, {})
        channels[frame.channel] = frame
        if 0 not in channels or 1 not in channels:
            continue
        pending.pop(frame.frame_id)
        if stereo is None or layer is None or tracker is None:
            continue
        calibration = config.calibration
        if calibration.focal_length_px <= 0 or calibration.baseline_m <= 0:
            continue
        rig = StereoRig(
            fx=calibration.focal_length_px,
            fy=calibration.focal_length_px,
            cx=calibration.cx,
            cy=calibration.cy,
            baseline_m=calibration.baseline_m,
        )
        left_frame, right_frame = channels[0], channels[1]
        try:
            points = stereo.reconstruct(
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
            continue
        sampled = points[:: max(1, len(points) // 4000)] if points else points
        runtime_pose: Pose | None = None
        if slam is not None:
            pair = StereoFramePair(
                frame.frame_id,
                frame.t_ns,
                "",
                "",
                "",
                left_frame.data,
                right_frame.data,
            )
            runtime_pose = slam.process_frame(pair).pose
            if runtime_pose is not None:
                sampled = tuple(to_map_frame(point, runtime_pose) for point in sampled)
        if layer.voxel_count == 0:
            layer.seed(sampled)
            continue
        clusters = layer.difference(frame.frame_id, frame.t_ns, sampled)
        candidate_ids = {id(point) for cluster in clusters for point in cluster.points}
        assert tracker is not None and verdicts is not None
        for cluster, observation in zip(clusters, areas_from_clusters(clusters), strict=True):
            track = tracker.update(observation)
            center = _centroid(cluster.points)
            stats = motion_stats.update(
                track.track_id, frame.t_ns, center, _polygon_area(observation.polygon)
            )
            update = verdicts.update(track.track_id, stats)
            final_verdicts[track.track_id] = update.verdict
            yield survey_pb2.MovingAreasResponse(
                area=survey_pb2.MovingArea(
                    frame_id=frame.frame_id,
                    t_ns=frame.t_ns,
                    polygon=[survey_pb2.Point2(x=x, y=y) for x, y in observation.polygon],
                    depth_min_m=observation.depth_min_m,
                    depth_max_m=observation.depth_max_m,
                    dynamic_point_count=observation.point_count,
                    area_track_id=track.track_id,
                    verdict=_VERDICT_PROTO[update.verdict.value],
                    verdict_version=update.version,
                )
            )
            if update.verdict is Verdict.RIGID_MOVER:
                previous = previous_centroids.get(track.track_id)
                velocity = Vec3(0.0, 0.0, 0.0)
                if previous is not None and frame.t_ns > previous[0]:
                    dt = (frame.t_ns - previous[0]) / 1e9
                    velocity = Vec3(
                        (center.x - previous[1].x) / dt,
                        (center.y - previous[1].y) / dt,
                        (center.z - previous[1].z) / dt,
                    )
                previous_centroids[track.track_id] = (frame.t_ns, center)
                observations.add(
                    track.track_id,
                    Observation(
                        t_ns=frame.t_ns,
                        keypoints=select_keypoints(cluster.points, base),
                        centroid=center,
                        velocity=velocity,
                        vo_translation=Vec3(0.0, 0.0, 0.0),
                    ),
                )
                buffered_frame_ids.setdefault(track.track_id, []).append(frame.frame_id)
        layer.observe_frame(point for point in sampled if id(point) not in candidate_ids)
    if config is None:
        raise ValueError("first request must be config")
    if slam is not None and layer is not None:
        flush = getattr(slam, "flush", None)
        results = await asyncio.to_thread(flush) if callable(flush) else []
        keyframes = tuple(
            KeyframePose(result.t_ns, result.pose) for result in results if result.pose is not None
        )
        cloud = [point for result in results for point in result.static_points]
        if cloud:
            layer.refresh(cloud)
        if keyframes:
            for track_id, frame_ids in buffered_frame_ids.items():
                buffered = observations.observations(track_id)
                if not buffered:
                    continue
                poses = distribute_correction(buffered, keyframes)
                track_id_out, _source = object_track_id(None, track_id)
                verdict_proto = _VERDICT_PROTO[final_verdicts[track_id].value]
                for obs, pose, fid in zip(buffered, poses, frame_ids, strict=True):
                    snapshot = build_snapshot(fid, obs, pose, track_id_out, "AREA_ALLOCATED")
                    yield survey_pb2.MovingAreasResponse(
                        snapshot=survey_pb2.MovingObjectSnapshot(
                            frame_id=snapshot.frame_id,
                            t_ns=snapshot.t_ns,
                            area_track_id=track_id,
                            object_track_id=snapshot.object_track_id,
                            identity_source=survey_pb2.IDENTITY_SOURCE_AREA_ALLOCATED,
                            verdict=verdict_proto,
                            keypoints=[
                                survey_pb2.Point3(x=k.x, y=k.y, z=k.z) for k in snapshot.keypoints
                            ],
                            centroid=survey_pb2.Point3(
                                x=snapshot.centroid.x,
                                y=snapshot.centroid.y,
                                z=snapshot.centroid.z,
                            ),
                            velocity=survey_pb2.Point3(
                                x=obs.velocity.x, y=obs.velocity.y, z=obs.velocity.z
                            ),
                        )
                    )
