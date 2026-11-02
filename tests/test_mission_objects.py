"""ObjectMerger: one track per object across frames."""

from __future__ import annotations

from surmap.mission.objects import ObjectMerger, object_summary
from surmap.types import ObjectPoints, ObjectTrack3D, Vec3


def _blob(x: float, y: float = 0.0, z: float = 2.0) -> tuple[Vec3, ...]:
    return tuple(
        Vec3(x + dx * 0.05, y + dy * 0.05, z) for dx in range(-3, 4) for dy in range(-3, 4)
    )


def test_a_mask_on_known_points_continues_the_bound_track() -> None:
    merger = ObjectMerger()
    first = merger.observe(1, "person", _blob(0.0))
    assert first is not None and first.track_id is None
    merger.bind(first, 7)

    again = merger.observe(2, "person", _blob(0.0))

    assert again is not None
    assert again.track_id == 7
    assert not again.moving


def test_a_different_label_on_the_same_points_is_a_different_object() -> None:
    merger = ObjectMerger()
    person = merger.observe(1, "person", _blob(0.0))
    assert person is not None
    merger.bind(person, 1)

    car = merger.observe(1, "car", _blob(0.0))

    assert car is not None and car.track_id is None


def test_far_apart_masks_are_separate_objects() -> None:
    merger = ObjectMerger()
    left = merger.observe(1, "person", _blob(0.0))
    assert left is not None
    merger.bind(left, 1)
    right = merger.observe(1, "person", _blob(5.0))
    assert right is not None and right.track_id is None


def test_drift_of_forty_centimetres_turns_the_object_moving_once() -> None:
    merger = ObjectMerger()
    first = merger.observe(1, "car", _blob(0.0))
    assert first is not None
    merger.bind(first, 1)

    shifted = merger.observe(2, "car", _blob(0.25))
    further = merger.observe(3, "car", _blob(0.45))
    again = merger.observe(4, "car", _blob(0.5))

    assert shifted is not None and shifted.track_id == 1 and not shifted.moving
    assert further is not None and further.track_id == 1
    assert further.moving and further.turned_moving
    assert again is not None and again.moving and not again.turned_moving


def test_no_points_is_no_sighting() -> None:
    assert ObjectMerger().observe(1, "person", ()) is None


def test_the_summary_is_one_line_per_track() -> None:
    track = ObjectTrack3D(
        track_id=1,
        label="person",
        observations=[ObjectPoints(1, frame_id, 0, (), Vec3(1.0, 2.0, 0.5)) for frame_id in (1, 2)],
    )
    assert object_summary([track]) == (
        "person, static, seen in 2 frame(s), map x=1.0 m y=2.0 m z=0.5 m",
    )
