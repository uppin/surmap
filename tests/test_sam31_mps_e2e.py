"""Real SAM 3.1 on this Mac's GPU (MPS); skipped without torch, sam3, Metal or the weights."""

import importlib
import importlib.util
import io
from pathlib import Path

import pytest
from PIL import Image

from surmap.survey.sam import RawFrame

KITTI = Path.home() / ".cache/surmap/demo-datasets/kitti-2011-09-26-drive-0009/mav0/cam0/data"
CHECKPOINTS = Path.home() / ".cache/huggingface/hub/models--facebook--sam3.1/snapshots"


def _checkpoint() -> Path:
    if importlib.util.find_spec("torch") is None or importlib.util.find_spec("sam3") is None:
        pytest.skip("the optional torch + sam3 stack is not installed")
    torch = importlib.import_module("torch")  # optional: not a typed dependency
    if not torch.backends.mps.is_available():
        pytest.skip("no Apple GPU (MPS) here")
    found = sorted(CHECKPOINTS.glob("*/sam3.1_multiplex.pt"))
    if not found or not KITTI.is_dir():
        pytest.skip("the SAM 3.1 checkpoint or the cached KITTI 0009 scene is missing")
    return found[0]


def test_sam31_finds_the_cars_of_a_kitti_street_on_the_apple_gpu() -> None:
    # Given SAM 3.1 on MPS, and a KITTI 0009 frame with parked cars
    from surmap.survey.sam3_torch import sam31_torch_detector

    detector = sam31_torch_detector(str(_checkpoint()), device="mps", prompt="car")
    frame_path = sorted(KITTI.glob("*.png"))[199]
    image = Image.open(frame_path).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    frame = RawFrame(200, 0, 0, image.width, image.height, "mjpeg", buffer.getvalue())

    # When the frame is segmented
    cars = detector.segment(frame)

    # Then the cars are found, each with an outline inside the frame
    assert len(cars) >= 3
    assert all(car.label == "car" and len(car.mask_polygon) >= 3 for car in cars)
    assert all(
        0 <= x <= image.width and 0 <= y <= image.height
        for car in cars
        for x, y in car.mask_polygon
    )
