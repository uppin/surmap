import io
import json
import pathlib

import numpy as np
import pytest
from PIL import Image

from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig, decode_grayscale

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "eth3d_cables2"


def load_rig() -> StereoRig:
    cal = json.loads((FIXTURE / "calibration.json").read_text(encoding="utf-8"))
    return StereoRig(cal["fx"], cal["fy"], cal["cx"], cal["cy"], cal["baseline_m"])


def load_frame(side: str, index: int = 0) -> FrameImage:
    data = (FIXTURE / f"{side}_{index:03d}.jpg").read_bytes()
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
    return FrameImage(width, height, "mjpeg", data)


def test_decoding_a_jpeg_frame_yields_a_grayscale_image_of_its_size() -> None:
    # Given one real fixture frame (640x397)
    gray = decode_grayscale(load_frame("left"))

    # Then it decodes to a single-channel float image of that size
    assert gray.shape == (397, 640)
    assert gray.dtype == np.float32


def test_decoding_a_raw_rgb_frame_converts_colour_to_gray() -> None:
    # Given a 2x1 raw RGB frame: one white pixel, one black pixel
    frame = FrameImage(2, 1, "raw_rgb", bytes([255, 255, 255, 0, 0, 0]))

    gray = decode_grayscale(frame)

    assert gray.shape == (1, 2)
    assert gray[0, 0] > 250.0
    assert gray[0, 1] < 5.0


def test_reconstruction_finds_the_tabletop_scene_in_a_real_pair() -> None:
    # Given the first real ETH3D pair and its calibration
    rig = load_rig()

    # When the pair is reconstructed
    points = StereoReconstructor().reconstruct(load_frame("left"), load_frame("right"), rig)

    # Then the scene is there: many points, all in front, sane depths
    assert len(points) > 500
    depths = sorted(p.z for p in points)
    assert depths[len(depths) // 2] == pytest.approx(0.6, abs=0.45)
    assert all(0.2 <= p.z <= 8.0 for p in points)


def test_a_featureless_pair_yields_no_points() -> None:
    # Given a smooth gradient on both channels — no texture to match.
    # (An identical *textured* photo is not used here: repetitive texture
    # legitimately self-matches at shifted positions, so it cannot
    # distinguish a broken matcher from a working one.)
    gradient = bytes(
        value for _row in range(48) for col in range(64) for value in (col * 4, col * 4, col * 4)
    )
    frame = FrameImage(64, 48, "raw_rgb", gradient)
    rig = load_rig()

    # Then nothing can be triangulated
    assert StereoReconstructor().reconstruct(frame, frame, rig) == ()
