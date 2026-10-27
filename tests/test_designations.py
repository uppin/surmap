import pytest

from surmap.survey.designations import (
    RTABMAP_DESIGNATION,
    object_designation,
    video_designation,
)


def test_rtabmap_scene_points_always_take_designation_one() -> None:
    # Then the static scene is told apart from every object and video output
    assert RTABMAP_DESIGNATION == 1


def test_left_and_right_video_channels_take_designations_two_and_three() -> None:
    # When the requester asks for a channel's frames back
    # Then channel 0 is designation 2 and channel 1 is designation 3
    assert video_designation(0) == 2
    assert video_designation(1) == 3


def test_a_video_channel_outside_the_stereo_pair_is_rejected() -> None:
    # Given the rig has exactly two fixed channels
    # When a third channel is designated
    with pytest.raises(ValueError, match="channel"):
        video_designation(2)


def test_each_tracked_object_is_grouped_under_its_own_designation() -> None:
    # Then objects start at 100 and never collide with scene or video
    assert object_designation(0) == 100
    assert object_designation(7) == 107


def test_a_negative_track_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="track_id"):
        object_designation(-1)
