"""Continuous (video) SAM tests: stateful tracking over sequential frames.

The real adapter runs the tiny fake SAM3 ONNX graph through the same
`Sam3VideoDetector` code the station GPU runs — only the weights, the
provider and the device differ.
"""

import io
from pathlib import Path

import pytest
from PIL import Image

from surmap.survey.sam import InMemoryVideoSamDetector, RawFrame, SamDetection
from surmap.survey.sam3 import (
    OnnxSam3Session,
    Sam3Unavailable,
    Sam3VideoDetector,
    parse_sam_device,
    sam3_video_detector,
)

FAKE_MODEL = Path(__file__).parent / "fixtures" / "sam3_fake" / "fake_sam3.onnx"


def _frame_with_bright_box(frame_id: int, x0: int) -> RawFrame:
    image = Image.new("RGB", (256, 256), (10, 10, 10))
    for x in range(x0, x0 + 80):
        for y in range(60, 140):
            image.putpixel((x, y), (240, 240, 240))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return RawFrame(frame_id, frame_id * 100, 0, 256, 256, "mjpeg", buffer.getvalue())


def test_a_gpu_device_string_names_its_cuda_index() -> None:
    # Given / When / Then the device strings a CLI user writes
    assert parse_sam_device("cuda:2") == ("cuda", 2)
    assert parse_sam_device("cuda") == ("cuda", 0)
    assert parse_sam_device("0") == ("cuda", 0)
    assert parse_sam_device("cpu") == ("cpu", None)
    assert parse_sam_device("auto") == ("auto", None)
    with pytest.raises(ValueError, match="unknown SAM device"):
        parse_sam_device("tpu:0")


def test_video_tracking_keeps_one_track_id_as_the_box_moves() -> None:
    # Given a SAM video session on the fake model (CPU twin of the GPU run)
    detector = Sam3VideoDetector(OnnxSam3Session(FAKE_MODEL, device="cpu"), label="fixture")

    # When the same bright box is tracked on two sequential frames
    first = detector.track(_frame_with_bright_box(1, x0=30))
    second = detector.track(_frame_with_bright_box(2, x0=40))

    # Then continuous mode carries one persistent track id, not per-frame ids
    assert len(first) == 1 and len(second) == 1
    assert first[0].track_id is not None
    assert second[0].track_id == first[0].track_id
    assert len(second[0].mask_polygon) >= 8


def test_reset_starts_a_new_video_with_fresh_track_ids() -> None:
    # Given a video session that already tracked a box
    detector = Sam3VideoDetector(OnnxSam3Session(FAKE_MODEL, device="cpu"), label="fixture")
    first_run = detector.track(_frame_with_bright_box(1, x0=30))

    # When the stream restarts
    detector.reset()
    restarted = detector.track(_frame_with_bright_box(1, x0=30))

    # Then ids restart from the first id of the new video
    assert restarted[0].track_id == first_run[0].track_id == 1


def test_the_video_factory_builds_a_session_for_the_named_device() -> None:
    # Given / When a video detector is built for the CPU twin device
    detector = sam3_video_detector(FAKE_MODEL, device="cpu", label="fixture")

    # Then it reports that provider and tracks a frame
    assert detector.provider == "CPUExecutionProvider"
    assert len(detector.track(_frame_with_bright_box(1, x0=30))) == 1
    detector.close()


def test_asking_for_cuda_without_a_cuda_provider_fails_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given an ONNX Runtime with no CUDA provider (this CI host)
    import importlib

    ort = importlib.import_module("onnxruntime")
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CPUExecutionProvider"])

    # When / Then building a GPU session names what is missing
    with pytest.raises(Sam3Unavailable, match="onnxruntime-gpu"):
        OnnxSam3Session(FAKE_MODEL, device="cuda:0")


def test_the_in_memory_video_detector_records_frames_in_order() -> None:
    # Given the test adapter configured with one untracked detection
    detector = InMemoryVideoSamDetector(
        (SamDetection("car", 0.9, (0.0, 0.0, 10.0, 10.0), ((1.0, 1.0), (2.0, 1.0))),)
    )

    # When two sequential frames are tracked
    first = detector.track(_frame_with_bright_box(1, x0=30))
    second = detector.track(_frame_with_bright_box(2, x0=40))

    # Then the configured detection gains a persistent id and frames are recorded
    assert [frame.frame_id for frame in detector.frames] == [1, 2]
    assert first[0].track_id == second[0].track_id == 1

    # And a reset starts the next video's recording afresh
    detector.reset()
    assert detector.frames == []
