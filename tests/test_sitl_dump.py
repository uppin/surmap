"""ROS 2 SITL dumper helpers that do not need rclpy."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from surmap.simulation.sitl_dump import image_msg_to_png, navsat_accuracy_m, take_stereo_pair


def test_navsat_accuracy_is_the_square_root_of_the_reported_variance() -> None:
    # Given a NavSatFix east-variance of 0.25 m²
    variance_m2 = 0.25

    # When the capture records horizontal accuracy
    accuracy_m = navsat_accuracy_m(variance_m2)

    # Then the value is in metres, not the covariance's square metres
    assert accuracy_m == 0.5


def test_a_non_positive_navsat_variance_falls_back_to_one_metre() -> None:
    # Given a fix that did not report a usable covariance
    # When accuracy is derived
    # Then the capture keeps the previous 1 m fallback
    assert navsat_accuracy_m(0.0) == 1.0
    assert navsat_accuracy_m(-4.0) == 1.0
    assert navsat_accuracy_m(math.nan) == 1.0


def test_unpaired_frames_older_than_twice_the_slop_are_dropped() -> None:
    # Given a left frame 100 ms older than the newest stamp, and a 20 ms slop
    left = {0: "old-left", 70_000_000: "recent-left"}
    right = {100_000_000: "right"}

    # When pairing runs
    pair = take_stereo_pair(left, right, slop_ns=20_000_000)

    # Then nothing pairs, and only the frame older than 40 ms is dropped
    assert pair is None
    assert 0 not in left
    assert left == {70_000_000: "recent-left"}
    assert right == {100_000_000: "right"}


def test_stamps_within_the_slop_become_one_stereo_pair() -> None:
    # Given a left and right stamp 10 ms apart, inside a 20 ms slop
    left = {1_000_000_000: "left"}
    right = {1_010_000_000: "right"}

    # When pairing runs
    pair = take_stereo_pair(left, right, slop_ns=20_000_000)

    # Then they leave the buffers as one pair keyed by the left stamp
    assert pair == (1_000_000_000, "left", "right")
    assert left == {}
    assert right == {}


def test_padded_mono8_rows_keep_only_the_pixels(tmp_path: Path) -> None:
    # Given a 2×2 mono image whose rows are padded to 4 bytes
    msg = SimpleNamespace(
        encoding="mono8",
        width=2,
        height=2,
        step=4,
        data=bytes([1, 2, 9, 9, 3, 4, 9, 9]),
    )
    target = tmp_path / "frame.png"

    # When the dumper writes a PNG
    image_msg_to_png(msg, target)

    # Then the padding bytes are not pixels
    with Image.open(target) as image:
        assert image.size == (2, 2)
        assert list(image.get_flattened_data()) == [1, 2, 3, 4]


def test_bgr8_rows_are_swapped_to_rgb_and_padding_is_dropped(tmp_path: Path) -> None:
    # Given one BGR pixel padded out to a step of 4
    msg = SimpleNamespace(
        encoding="bgr8",
        width=1,
        height=1,
        step=4,
        data=bytes([10, 20, 30, 255]),
    )
    target = tmp_path / "frame.png"

    # When the dumper writes a PNG
    image_msg_to_png(msg, target)

    # Then the pixel is RGB and the pad byte is gone
    with Image.open(target) as image:
        assert image.mode == "RGB"
        assert list(image.get_flattened_data()) == [(30, 20, 10)]
