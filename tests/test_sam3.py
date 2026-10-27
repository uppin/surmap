"""SAM 3.1 adapter tests over the fake ONNX model.

The fake model is a real ONNX graph run by the same `OnnxSam3Session`
(ONNX Runtime, CPU provider here; CUDA on the station GPU) and the
same `Sam3Detector` preprocessing/post-processing as production —
only the weights and provider differ.
"""

import io
from pathlib import Path

import pytest
from PIL import Image

from surmap.survey.sam import RawFrame
from surmap.survey.sam3 import OnnxSam3Session, Sam3Detector, Sam3Unavailable

FAKE_MODEL = Path(__file__).parent / "fixtures" / "sam3_fake" / "fake_sam3.onnx"


def _frame_with_bright_box(frame_id: int = 1, x0: int = 30) -> RawFrame:
    image = Image.new("RGB", (256, 256), (10, 10, 10))
    for x in range(x0, x0 + 80):
        for y in range(60, 140):
            image.putpixel((x, y), (240, 240, 240))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return RawFrame(frame_id, frame_id * 100, 0, 256, 256, "mjpeg", buffer.getvalue())


def test_the_fake_model_runs_through_onnx_runtime_on_cpu() -> None:
    session = OnnxSam3Session(FAKE_MODEL, device="cpu")
    assert session.provider == "CPUExecutionProvider"
    assert session.input_size == (256, 256)


def test_a_missing_model_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(Sam3Unavailable, match="provision it"):
        OnnxSam3Session(tmp_path / "nope.onnx", device="cpu")


async def test_the_detector_segments_a_bright_region_with_a_polygon() -> None:
    detector = Sam3Detector(OnnxSam3Session(FAKE_MODEL, device="cpu"), label="fixture")
    (detection,) = await detector.detect(_frame_with_bright_box())
    assert detection.label == "fixture"
    x_min, y_min, x_max, y_max = detection.box_xyxy
    assert abs(x_min - 30) <= 3 and abs(x_max - 110) <= 3
    assert abs(y_min - 60) <= 3 and abs(y_max - 140) <= 3
    assert len(detection.mask_polygon) >= 8


async def test_the_detector_tracks_nothing_in_a_dark_frame() -> None:
    detector = Sam3Detector(OnnxSam3Session(FAKE_MODEL, device="cpu"))
    image = Image.new("RGB", (256, 256), (5, 5, 5))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    frame = RawFrame(1, 100, 0, 256, 256, "mjpeg", buffer.getvalue())
    assert await detector.detect(frame) == ()


def test_station_entrypoint_accepts_a_sam3_detector() -> None:
    from surmap.survey.sam3 import sam3_detector
    from surmap.survey.station_main import build_description

    detector = sam3_detector(FAKE_MODEL, device="cpu")
    assert detector.provider == "CPUExecutionProvider"
    description = build_description(detector=detector)
    assert [m.descriptor.full_name for m in description.services] == [
        "surmap.survey.v1.StationSamService"
    ]
