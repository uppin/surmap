"""Red tests for n5: retrospective placement."""

from __future__ import annotations

from surmap.moving.buffer import Observation
from surmap.moving.placement import (
    AREA_TRACK_ID_BASE,
    KeyframePose,
    distribute_correction,
    object_track_id,
)
from surmap.types import Pose, Vec3


def _obs(t_ns: int, vo_x: float) -> Observation:
    return Observation(
        t_ns=t_ns,
        keypoints=(Vec3(0.0, 0.0, 5.0),),
        centroid=Vec3(0.0, 0.0, 5.0),
        velocity=Vec3(0.0, 0.0, 0.0),
        vo_translation=Vec3(vo_x, 0.0, 0.0),
    )


def test_correction_is_distributed_not_interpolated() -> None:
    """VO chain says 1 m steps; keyframes correct the end by +0.3 m."""
    observations = tuple(_obs(i * 1_000_000_000, 1.0) for i in range(4))
    keyframes = (
        KeyframePose(0, Pose(Vec3(0.0, 0.0, 0.0))),
        KeyframePose(3_000_000_000, Pose(Vec3(3.3, 0.0, 0.0))),
    )
    poses = distribute_correction(observations, keyframes)
    assert len(poses) == 4
    assert poses[0].position.x == 0.0
    assert abs(poses[-1].position.x - 3.3) < 1e-9
    # distributed: middle pose carries roughly half the correction (0.15)
    assert abs(poses[1].position.x - 1.1) < 0.05


def test_detector_identity_is_adopted() -> None:
    track_id, source = object_track_id(detector_track_id=7, area_track_id=3)
    assert track_id == 7
    assert source == "DETECTOR"


def test_area_allocation_is_disjoint_from_detector_ids() -> None:
    track_id, source = object_track_id(detector_track_id=None, area_track_id=3)
    assert track_id == AREA_TRACK_ID_BASE + 3
    assert source == "AREA_ALLOCATED"
