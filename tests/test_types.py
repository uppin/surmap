from surmap.types import Detection, Track, Vec3


def test_vec3_subtraction_and_norm() -> None:
    assert Vec3(3, 0, 4) - Vec3(0, 0, 0) == Vec3(3, 0, 4)
    assert Vec3(3, 0, 4).norm() == 5.0


def test_track_frame_range() -> None:
    assert Track(7, "car").first_seen_frame is None
    track = Track(
        7,
        "car",
        [
            Detection(3, (0, 0, 1, 1), "car", 0.9, "det-v1"),
            Detection(5, (0, 0, 1, 1), "car", 0.8, "det-v1"),
        ],
    )
    assert track.first_seen_frame == 3
    assert track.last_seen_frame == 5
