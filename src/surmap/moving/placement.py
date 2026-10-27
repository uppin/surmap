"""Stage 6: retrospective map-frame placement (design section 4 step 6)."""

from __future__ import annotations

from dataclasses import dataclass

from surmap.geometry import to_map_frame
from surmap.moving.buffer import Observation
from surmap.types import Pose, Vec3

AREA_TRACK_ID_BASE = 1_000_000


@dataclass(frozen=True)
class KeyframePose:
    """One optimized keyframe pose from the RTAB flush."""

    t_ns: int
    pose: Pose


@dataclass(frozen=True)
class PlacedSnapshot:
    """One buffered observation placed in the map frame."""

    frame_id: int
    t_ns: int
    object_track_id: int
    identity_source: str  # DETECTOR | AREA_ALLOCATED
    keypoints: tuple[Vec3, ...]
    centroid: Vec3


def _nlerp(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    fraction: float,
) -> tuple[float, float, float, float]:
    mixed = tuple(x + (y - x) * fraction for x, y in zip(a, b, strict=True))
    norm = sum(value * value for value in mixed) ** 0.5 or 1.0
    return tuple(value / norm for value in mixed)  # type: ignore[return-value]


def distribute_correction(
    observations: tuple[Observation, ...],
    keyframes: tuple[KeyframePose, ...],
) -> tuple[Pose, ...]:
    """Camera pose per observation, keyframe correction over VO increments.

    The VO chain (cumulative `vo_translation` increments) is kept,
    and the correction between the chain and the optimized
    keyframe poses at the bracketing keyframes is distributed
    proportionally along the chain — pose-graph-lite, not linear
    interpolation between keyframes.
    """
    if not observations:
        return ()
    if not keyframes:
        raise ValueError("placement needs at least one keyframe pose")
    chain: list[Vec3] = [Vec3(0.0, 0.0, 0.0)]
    for observation in observations[1:]:
        previous = chain[-1]
        step = observation.vo_translation
        chain.append(Vec3(previous.x + step.x, previous.y + step.y, previous.z + step.z))
    first_kf = keyframes[0]
    last_kf = keyframes[-1]
    start_chain = chain[0]
    # Chain value at the last keyframe's time: the last observation
    # at or before it (observations are time-ordered).
    end_chain = chain[-1]
    correction = Vec3(
        last_kf.pose.position.x - (first_kf.pose.position.x + end_chain.x - start_chain.x),
        last_kf.pose.position.y - (first_kf.pose.position.y + end_chain.y - start_chain.y),
        last_kf.pose.position.z - (first_kf.pose.position.z + end_chain.z - start_chain.z),
    )
    span_ns = max(last_kf.t_ns - first_kf.t_ns, 1)
    poses: list[Pose] = []
    for observation, chain_point in zip(observations, chain, strict=True):
        fraction = (observation.t_ns - first_kf.t_ns) / span_ns
        fraction = min(1.0, max(0.0, fraction))
        position = Vec3(
            first_kf.pose.position.x + (chain_point.x - start_chain.x) + correction.x * fraction,
            first_kf.pose.position.y + (chain_point.y - start_chain.y) + correction.y * fraction,
            first_kf.pose.position.z + (chain_point.z - start_chain.z) + correction.z * fraction,
        )
        poses.append(
            Pose(position, _nlerp(first_kf.pose.orientation_xyzw,
                                   last_kf.pose.orientation_xyzw, fraction))
        )
    return tuple(poses)


def object_track_id(detector_track_id: int | None, area_track_id: int) -> tuple[int, str]:
    """Designation source: adopted detector ID or disjoint area allocation."""
    if detector_track_id is not None:
        return detector_track_id, "DETECTOR"
    return AREA_TRACK_ID_BASE + area_track_id, "AREA_ALLOCATED"


def build_snapshot(
    frame_id: int,
    observation: Observation,
    pose: Pose,
    track_id: int,
    identity_source: str,
) -> PlacedSnapshot:
    """Place one buffered observation in the map frame."""
    return PlacedSnapshot(
        frame_id=frame_id,
        t_ns=observation.t_ns,
        object_track_id=track_id,
        identity_source=identity_source,
        keypoints=tuple(to_map_frame(point, pose) for point in observation.keypoints),
        centroid=to_map_frame(observation.centroid, pose),
    )
