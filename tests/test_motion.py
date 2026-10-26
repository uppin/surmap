import pytest

from surmap.motion import classify_motion
from surmap.types import Motion, ObjectPoints, ObjectTrack3D, Vec3


def _obs(track_id: int, frame: int, centroid: Vec3) -> ObjectPoints:
    return ObjectPoints(track_id, frame, frame * 1_000_000, (centroid,), centroid)


def test_static_object() -> None:
    track = ObjectTrack3D(1, "car", [_obs(1, 1, Vec3(1, 0, 0)), _obs(1, 2, Vec3(1.1, 0, 0))])
    assert classify_motion(track, threshold_m=0.5) is Motion.STATIC


def test_moving_object() -> None:
    track = ObjectTrack3D(1, "car", [_obs(1, 1, Vec3(0, 0, 0)), _obs(1, 2, Vec3(3, 0, 0))])
    assert classify_motion(track, threshold_m=0.5) is Motion.MOVING


def test_too_few_observations_is_unknown() -> None:
    track = ObjectTrack3D(1, "car", [_obs(1, 1, Vec3(0, 0, 0))])
    assert classify_motion(track) is Motion.UNKNOWN


def test_negative_threshold_rejected() -> None:
    with pytest.raises(ValueError):
        classify_motion(ObjectTrack3D(1, "car"), threshold_m=-0.1)
