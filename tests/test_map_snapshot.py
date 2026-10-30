"""GPS-anchored semantic map snapshot.

The export is one UTF-8 JSON file. Moving tracks stay under ``dynamic``.
GeoJSON is not this file.
"""

import json
from pathlib import Path

import pytest

from surmap.map.snapshot import build_snapshot, read_snapshot, write_snapshot
from surmap.types import GpsCheckpoint, Motion, ObjectPoints, ObjectTrack3D, Vec3


def _checkpoint(
    t_ns: int,
    lat: float = 54.0,
    lon: float = 25.0,
    alt: float = 100.0,
    accuracy_m: float = 2.5,
) -> GpsCheckpoint:
    return GpsCheckpoint(t_ns, lat, lon, alt, accuracy_m)


def _track(track_id: int, label: str, sightings: list[tuple[int, Vec3]]) -> ObjectTrack3D:
    observations = [
        ObjectPoints(track_id, frame_id=index + 1, t_ns=t_ns, points=(centroid,), centroid=centroid)
        for index, (t_ns, centroid) in enumerate(sightings)
    ]
    return ObjectTrack3D(track_id, label, observations)


def test_static_landmark_is_anchored_and_the_moving_track_stays_dynamic(tmp_path: Path) -> None:
    # Given two fixes, a still roof, and a car that moves past the motion threshold
    early = _checkpoint(1_000_000_000, lat=54.0, lon=25.0, alt=100.0)
    late = _checkpoint(5_000_000_000, lat=54.01, lon=25.01, alt=110.0)
    roof = _track(
        7,
        "roof",
        [(1_000_000_000, Vec3(0.0, 0.0, 0.0)), (1_250_000_000, Vec3(0.0, 0.0, 0.0))],
    )
    car = _track(
        8,
        "car",
        [(4_000_000_000, Vec3(0.0, 0.0, 1.0)), (4_800_000_000, Vec3(3.0, 0.0, 1.0))],
    )
    cloud = (Vec3(0.2, 0.0, 0.0), Vec3(0.25, 0.05, 0.0))
    destination = tmp_path / "map.json"

    # When the snapshot is written
    snapshot = build_snapshot(
        [roof, car],
        [late, early],
        descriptions={7: "flat roof"},
        model_ids={7: "baseten/muse-spark-open"},
        mask_points={7: cloud},
    )
    write_snapshot(snapshot, destination)
    document = json.loads(destination.read_text(encoding="utf-8"))

    # Then the roof is a static landmark with a non-zero offset, and the car is only dynamic
    assert document["schema"] == "surmap.semantic_map_snapshot.v1"
    assert document["origin"] == {
        "t_ns": 1_000_000_000,
        "lat": 54.0,
        "lon": 25.0,
        "alt": 100.0,
        "accuracy_m": 2.5,
    }
    assert [item["id"] for item in document["landmarks"]] == ["7"]
    roof_json = document["landmarks"][0]
    assert roof_json["id"] == "7"
    assert roof_json["offset_ns"] == 250_000_000
    assert roof_json["anchor_t_ns"] == 1_000_000_000
    assert roof_json["t_ns"] == 1_250_000_000
    assert roof_json["motion"] == "static"
    assert roof_json["label"] == "roof"
    assert roof_json["description"] == "flat roof"
    assert roof_json["model_id"] == "baseten/muse-spark-open"
    assert roof_json["xyz"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert roof_json["lat"] == 54.0
    assert roof_json["lon"] == 25.0
    assert roof_json["alt"] == 100.0
    assert roof_json["mask_points"] == [
        {"x": 0.2, "y": 0.0, "z": 0.0},
        {"x": 0.25, "y": 0.05, "z": 0.0},
    ]
    assert roof_json["observations"] == [
        {"t_ns": 1_000_000_000, "xyz": {"x": 0.0, "y": 0.0, "z": 0.0}},
        {"t_ns": 1_250_000_000, "xyz": {"x": 0.0, "y": 0.0, "z": 0.0}},
    ]
    assert [item["id"] for item in document["dynamic"]] == ["8"]
    car_json = document["dynamic"][0]
    assert car_json["motion"] == "moving"
    assert car_json["mask_points"] is None
    assert car_json["offset_ns"] == -200_000_000
    assert car_json["xyz"] == {"x": 3.0, "y": 0.0, "z": 1.0}
    assert car_json["observations"] == [
        {"t_ns": 4_000_000_000, "xyz": {"x": 0.0, "y": 0.0, "z": 1.0}},
        {"t_ns": 4_800_000_000, "xyz": {"x": 3.0, "y": 0.0, "z": 1.0}},
    ]


def test_written_snapshot_reads_back_equal(tmp_path: Path) -> None:
    # Given a snapshot whose description is not ASCII and whose roof carries a mask cloud
    roof = _track(
        7,
        "stogas",
        [(1_250_000_000, Vec3(1.0, 2.0, 3.0)), (1_250_000_000, Vec3(1.0, 2.0, 3.0))],
    )
    car = _track(
        8,
        "car",
        [(4_000_000_000, Vec3(0.0, 0.0, 0.0)), (4_800_000_000, Vec3(3.0, 0.0, 0.0))],
    )
    cloud = (Vec3(1.0, 2.0, 3.0), Vec3(1.25, 2.0, 3.0))
    snapshot = build_snapshot(
        [roof, car],
        [_checkpoint(1_000_000_000), _checkpoint(5_000_000_000, lat=54.01, lon=25.01, alt=110.0)],
        descriptions={7: "šiaurės stogas"},
        model_ids={7: "baseten/muse-spark-open"},
        mask_points={7: cloud},
    )
    destination = tmp_path / "map.json"

    # When it is written and read back
    write_snapshot(snapshot, destination)
    loaded = read_snapshot(destination)

    # Then the loaded snapshot equals the written one, and the file is UTF-8
    text = destination.read_bytes().decode("utf-8")
    assert "šiaurės stogas" in text
    assert loaded == snapshot


def test_snapshot_with_no_fix_has_no_origin_and_null_coordinates() -> None:
    # Given a still door and no GPS fix
    track = _track(1, "door", [(100, Vec3(1.0, 2.0, 3.0)), (200, Vec3(1.0, 2.0, 3.0))])

    # When the snapshot is built
    snapshot = build_snapshot([track], [])

    # Then the origin is absent and the landmark has no geodetic position
    landmark = snapshot.landmarks[0]
    assert snapshot.origin is None
    assert landmark.lat is None
    assert landmark.lon is None
    assert landmark.alt is None
    assert landmark.offset_ns is None
    assert landmark.anchor_t_ns is None
    assert landmark.xyz == Vec3(1.0, 2.0, 3.0)


def test_geodetic_position_follows_the_origin_not_the_nearest_fix() -> None:
    # Given a landmark seen at a later fix, sitting on the map origin
    origin = _checkpoint(0, lat=10.0, lon=20.0, alt=5.0)
    later = _checkpoint(1_000, lat=11.0, lon=21.0, alt=9.0)
    track = _track(1, "post", [(1_000, Vec3(0.0, 0.0, 0.0)), (1_000, Vec3(0.0, 0.0, 0.0))])

    # When the snapshot is built
    snapshot = build_snapshot([track], [later, origin])

    # Then the position is the earlier fix, and the time offset is to the later fix
    landmark = snapshot.landmarks[0]
    assert snapshot.origin is not None
    assert snapshot.origin.t_ns == 0
    assert landmark.lat == 10.0
    assert landmark.lon == 20.0
    assert landmark.alt == 5.0
    assert landmark.anchor_t_ns == 1_000
    assert landmark.offset_ns == 0


def test_map_east_and_north_shift_longitude_and_latitude() -> None:
    # Given a landmark 111320 m east and north of an equatorial origin, and 5 m up
    origin = _checkpoint(0, lat=0.0, lon=0.0, alt=10.0)
    moved = Vec3(111_320.0, 111_320.0, 5.0)
    track = _track(1, "marker", [(1, moved), (2, moved)])

    # When the snapshot is built
    landmark = build_snapshot([track], [origin]).landmarks[0]

    # Then one degree of latitude, one degree of longitude, and five metres of altitude are added
    assert landmark.lat == 1.0
    assert landmark.lon == 1.0
    assert landmark.alt == 15.0


def test_landmark_id_is_the_decimal_track_id() -> None:
    # Given a track whose id is 42
    track = _track(42, "roof", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(0.0, 0.0, 0.0))])

    # When the snapshot is built
    landmark = build_snapshot([track], [_checkpoint(0)]).landmarks[0]

    # Then the landmark id is that track id in decimal
    assert landmark.id == "42"


def test_omitted_mask_cloud_is_null_and_an_empty_cloud_stays_empty() -> None:
    # Given one roof with a mask cloud and one door with an empty cloud
    roof = _track(7, "roof", [(10, Vec3(0.0, 0.0, 0.0)), (20, Vec3(0.0, 0.0, 0.0))])
    door = _track(8, "door", [(10, Vec3(1.0, 0.0, 0.0)), (20, Vec3(1.0, 0.0, 0.0))])
    cloud = (Vec3(0.1, 0.2, 0.3), Vec3(0.4, 0.5, 0.6))

    # When only the roof cloud is attached, and the door cloud is empty
    attached = build_snapshot([roof, door], [_checkpoint(0)], mask_points={7: cloud, 8: ()})
    omitted = build_snapshot([roof], [_checkpoint(0)])

    # Then an omitted cloud is null and an attached empty cloud is an empty list
    by_id = {landmark.id: landmark for landmark in attached.landmarks}
    assert by_id["7"].mask_points == cloud
    assert by_id["8"].mask_points == ()
    assert omitted.landmarks[0].mask_points is None


def test_moving_mask_cloud_stays_on_the_dynamic_track() -> None:
    # Given a still roof and a moving car that owns the only mask cloud
    still = _track(1, "roof", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(0.0, 0.0, 0.0))])
    moving = _track(2, "car", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(4.0, 0.0, 0.0))])
    cloud = (Vec3(4.0, 0.0, 0.0),)

    # When the snapshot is built
    snapshot = build_snapshot([still, moving], [_checkpoint(0)], mask_points={2: cloud})

    # Then the cloud stays on the dynamic car and is not copied onto the roof
    assert snapshot.landmarks[0].id == "1"
    assert snapshot.landmarks[0].mask_points is None
    assert snapshot.dynamic[0].id == "2"
    assert snapshot.dynamic[0].mask_points == cloud


def test_single_sighting_is_a_landmark_marked_unknown() -> None:
    # Given a bin seen once
    track = _track(3, "bin", [(500, Vec3(1.0, 0.0, 0.0))])

    # When the snapshot is built
    snapshot = build_snapshot([track], [_checkpoint(400)])

    # Then it is a landmark marked unknown, not a dynamic track
    assert snapshot.dynamic == ()
    assert snapshot.landmarks[0].id == "3"
    assert snapshot.landmarks[0].motion is Motion.UNKNOWN
    assert snapshot.landmarks[0].offset_ns == 100


def test_stored_static_flag_does_not_keep_a_moving_track_out_of_dynamic() -> None:
    # Given a track already marked static whose centroid then moves 3 m
    track = _track(5, "car", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(3.0, 0.0, 0.0))])
    track.motion = Motion.STATIC

    # When the snapshot is built
    snapshot = build_snapshot([track], [_checkpoint(0)])

    # Then classify_motion puts it under dynamic
    assert snapshot.landmarks == ()
    assert snapshot.dynamic[0].motion is Motion.MOVING


def test_centroid_shift_at_the_motion_threshold_stays_a_landmark() -> None:
    # Given a car whose centroid moves by exactly the default threshold
    track = _track(1, "car", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(0.5, 0.0, 0.0))])

    # When the snapshot is built
    snapshot = build_snapshot([track], [_checkpoint(0)])

    # Then it is still a static landmark
    assert snapshot.dynamic == ()
    assert snapshot.landmarks[0].motion is Motion.STATIC


def test_equally_near_fixes_anchor_the_landmark_to_the_earlier_fix() -> None:
    # Given two fixes the same distance in time from the sighting
    early = _checkpoint(0, lat=1.0, lon=2.0, alt=3.0)
    late = _checkpoint(2_000, lat=9.0, lon=9.0, alt=9.0)
    track = _track(1, "post", [(1_000, Vec3(0.0, 0.0, 0.0)), (1_000, Vec3(0.0, 0.0, 0.0))])

    # When the snapshot is built
    landmark = build_snapshot([track], [late, early]).landmarks[0]

    # Then the earlier fix wins
    assert landmark.anchor_t_ns == 0
    assert landmark.offset_ns == 1_000


def test_landmark_position_is_the_latest_map_centroid() -> None:
    # Given a still door whose centroid shifts by less than the motion threshold
    track = _track(1, "door", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(0.1, 0.2, 0.3))])

    # When the snapshot is built
    landmark = build_snapshot([track], [_checkpoint(0)]).landmarks[0]

    # Then the landmark position is the latest centroid, and both sightings are kept
    assert landmark.xyz == Vec3(0.1, 0.2, 0.3)
    assert [observation.xyz for observation in landmark.observations] == [
        Vec3(0.0, 0.0, 0.0),
        Vec3(0.1, 0.2, 0.3),
    ]
    assert [observation.t_ns for observation in landmark.observations] == [1, 2]


def test_track_with_no_sightings_is_left_out() -> None:
    # Given a track that was never observed, and one fix
    snapshot = build_snapshot([ObjectTrack3D(1, "ghost")], [_checkpoint(1, accuracy_m=1.5)])

    # When the snapshot is built, the track is absent and the origin remains
    assert snapshot.landmarks == ()
    assert snapshot.dynamic == ()
    assert snapshot.origin is not None
    assert snapshot.origin.t_ns == 1
    assert snapshot.origin.accuracy_m == 1.5


def test_duplicate_track_ids_are_rejected() -> None:
    # Given two tracks that claim the same id
    first = _track(1, "a", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(0.0, 0.0, 0.0))])
    second = _track(1, "b", [(1, Vec3(1.0, 0.0, 0.0)), (2, Vec3(1.0, 0.0, 0.0))])

    # When the snapshot is built
    # Then the duplicate id is rejected
    with pytest.raises(ValueError, match="track"):
        build_snapshot([first, second], [_checkpoint(0)])


def test_landmark_keeps_label_description_and_model_id() -> None:
    # Given a roof with a description and a model id
    track = _track(4, "roof", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(0.0, 0.0, 0.0))])

    # When the snapshot is built
    landmark = build_snapshot(
        [track],
        [_checkpoint(0)],
        descriptions={4: "flat concrete roof"},
        model_ids={4: "baseten/muse-spark-open"},
    ).landmarks[0]

    # Then those three texts are stored on the landmark
    assert landmark.label == "roof"
    assert landmark.description == "flat concrete roof"
    assert landmark.model_id == "baseten/muse-spark-open"


def test_missing_description_and_model_id_are_empty_strings() -> None:
    # Given a roof with no description and no model id
    track = _track(4, "roof", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(0.0, 0.0, 0.0))])

    # When the snapshot is built
    landmark = build_snapshot([track], [_checkpoint(0)]).landmarks[0]

    # Then both texts are empty
    assert landmark.description == ""
    assert landmark.model_id == ""


def test_landmarks_are_ordered_by_track_id() -> None:
    # Given two still tracks passed with the higher id first
    later = _track(9, "b", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(0.0, 0.0, 0.0))])
    earlier = _track(2, "a", [(1, Vec3(0.0, 0.0, 0.0)), (2, Vec3(0.0, 0.0, 0.0))])

    # When the snapshot is built
    snapshot = build_snapshot([later, earlier], [_checkpoint(0)])

    # Then the landmarks are ordered by track id
    assert [landmark.id for landmark in snapshot.landmarks] == ["2", "9"]


def test_read_snapshot_rejects_an_unknown_schema(tmp_path: Path) -> None:
    # Given a JSON file that is not this snapshot schema
    path = tmp_path / "map.json"
    path.write_text('{"schema": "other"}', encoding="utf-8")

    # When it is read
    # Then the schema is rejected
    with pytest.raises(ValueError, match="schema"):
        read_snapshot(path)
