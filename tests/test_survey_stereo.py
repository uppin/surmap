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


def _shifted_pair(
    disparity_px: float, width: int = 320, height: int = 64
) -> tuple[FrameImage, FrameImage]:
    """Textured left frame and a right frame shifted by a fractional disparity."""
    rng = np.random.default_rng(7)
    # Blocky high-contrast texture: unambiguous to match, and the
    # fractional shift still yields a smooth cost minimum.
    blocks = rng.random((height // 4 + 2, (width + 64) // 4 + 2)).astype(np.float32)
    texture = np.repeat(np.repeat(blocks, 4, axis=0), 4, axis=1)[:height, : width + 64]
    kernel = np.ones(3, dtype=np.float32) / 3.0
    texture = np.apply_along_axis(lambda row: np.convolve(row, kernel, mode="same"), 1, texture)
    # The matcher pairs left[x] with right[x + d], so the right
    # frame holds the left texture shifted by -disparity.
    left = texture[:, 32 : 32 + width]
    cols = np.arange(width, dtype=np.float64) + 32.0
    right = np.stack(
        [
            np.interp(cols - disparity_px, np.arange(width + 64, dtype=np.float64), row)
            for row in texture
        ]
    )

    def frame(image: np.ndarray) -> FrameImage:
        pixels = np.clip(image / max(float(image.max()), 1e-9) * 255.0, 0, 255).astype(np.uint8)
        return FrameImage(
            width, height, "raw_rgb", np.repeat(pixels[:, :, None], 3, axis=2).tobytes()
        )

    return frame(left), frame(right)


def test_subpixel_disparity_recovers_a_fractional_disparity_depth() -> None:
    # Given a fronto-parallel textured plane whose true disparity is
    # fractional at the matching scale (12.5 px at half width), so an
    # integer-disparity matcher lands on a depth shell ~4% off.
    left, right = _shifted_pair(disparity_px=25.0)
    rig = StereoRig(fx=100.0, fy=100.0, cx=160.0, cy=32.0, baseline_m=0.5)

    # When the pair is reconstructed
    points = StereoReconstructor(max_disparity=64, max_depth_m=10.0).reconstruct(left, right, rig)

    # Then the median depth is the true 2.0 m, not the 1.92/2.08 m shell
    assert len(points) > 200
    depths = sorted(p.z for p in points)
    assert depths[len(depths) // 2] == pytest.approx(2.0, abs=0.06)


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
