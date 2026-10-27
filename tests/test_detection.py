"""Detection package tests: tracker logic, detector output parsing
with a fake interpreter, and object-point lifting with a stub source.
The real model is exercised by the Coral E2E.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.detection.detector import CoralDetector, DetectorUnavailable
from surmap.detection.source import CoralObjectPointSource
from surmap.detection.tracker import IouTracker, TrackedDetection
from surmap.types import Detection, Pose, StereoFramePair, Vec3


def _detection(
    frame_id: int, box: tuple[float, float, float, float], label: str = "car"
) -> Detection:
    return Detection(frame_id, box, label, 0.9, "fake-model")


def test_tracker_keeps_ids_for_moving_boxes_and_expires_stale_tracks() -> None:
    tracker = IouTracker(iou_threshold=0.2, max_missed=1)
    first = tracker.update(1, (_detection(1, (0.0, 0.0, 20.0, 20.0)),))
    second = tracker.update(2, (_detection(2, (4.0, 0.0, 24.0, 20.0)),))
    other_label = tracker.update(3, (_detection(3, (4.0, 0.0, 24.0, 20.0), label="bus"),))
    assert first[0].track_id == second[0].track_id == 1
    assert other_label[0].track_id == 2  # different label never matches
    tracker.update(5, ())
    assert tracker.live_track_ids == ()  # both expired after max_missed


class _FakeInterpreter:
    def __init__(self, **_kwargs: Any) -> None:
        self.invoked = False

    def allocate_tensors(self) -> None:
        pass

    def get_input_details(self) -> list[dict[str, Any]]:
        return [{"shape": [1, 320, 320, 3], "index": 0}]

    def get_output_details(self) -> list[dict[str, Any]]:
        return [{"index": 10}, {"index": 11}, {"index": 12}, {"index": 13}]

    def set_tensor(self, index: int, value: NDArray[np.uint8]) -> None:
        assert value.shape == (1, 320, 320, 3)

    def invoke(self) -> None:
        self.invoked = True

    def get_tensor(self, index: int) -> NDArray[Any]:
        return {
            10: np.array([[[0.1, 0.2, 0.5, 0.6]]], dtype=np.float32),  # yx yx normalized
            11: np.array([[2.0]], dtype=np.float32),
            12: np.array([[0.9]], dtype=np.float32),
            13: np.array([1.0], dtype=np.float32),
        }[index]


def test_detector_parses_efficientdet_outputs(tmp_path: Path) -> None:
    model = tmp_path / "model.tflite"
    model.write_bytes(b"fake")
    labels = tmp_path / "labels.txt"
    labels.write_text("person\nbicycle\ncar\n", encoding="utf-8")
    detector = CoralDetector(model, labels, interpreter_factory=_FakeInterpreter)
    (detection,) = detector.detect(np.zeros((100, 200, 3), dtype=np.uint8), frame_id=7)
    assert detection.label == "car"
    assert detection.frame_id == 7
    assert detection.box_xyxy == pytest.approx((40.0, 10.0, 120.0, 50.0))


def test_coral_source_selects_the_requested_profile_twin(tmp_path: Path) -> None:
    from surmap.detection.profiles import MODEL_PROFILES
    from surmap.survey.cm5_main import coral_source

    (tmp_path / "coco_labels.txt").write_text("person\ncar\n", encoding="utf-8")
    for profile in MODEL_PROFILES.values():
        (tmp_path / profile.edgetpu_file).write_bytes(b"x")
        (tmp_path / profile.cpu_file).write_bytes(b"x")

    cpu = coral_source(tmp_path, model="ssdlite-mobiledet")
    tpu = coral_source(tmp_path, model="ssdlite-mobiledet", use_edgetpu=True)
    assert cpu.model_id == "ssdlite_mobiledet_coco_qat_postprocess.tflite"
    assert tpu.model_id == "ssdlite_mobiledet_coco_qat_postprocess_edgetpu.tflite"
    assert coral_source(tmp_path).model_id == "efficientdet_lite0_320_ptq.tflite"


def test_detector_requires_a_prepared_model(tmp_path: Path) -> None:
    with pytest.raises(DetectorUnavailable, match="fetch_coral_model"):
        CoralDetector(tmp_path / "missing.tflite", tmp_path / "labels.txt")


class _StubSource:
    def detect_tracked(self, frame_id: int, rgb: NDArray[np.uint8]) -> tuple[TrackedDetection, ...]:
        return (TrackedDetection("car", 0.9, (0.0, 0.0, 100.0, 100.0), 5, frame_id),)


class _StubStereo:
    def reconstruct(self, left: object, right: object, rig: object) -> tuple[Vec3, ...]:
        return (
            Vec3(0.0, 0.0, 1.0),
            Vec3(0.01, 0.0, 1.0),
            Vec3(0.0, 0.01, 1.0),
            Vec3(5.0, 5.0, 1.0),
        )


def _jpeg_bytes() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (100, 110, 120)).save(buffer, format="JPEG")
    return buffer.getvalue()


async def test_detections_stream_is_separate_and_keyed_by_frame_id() -> None:
    from surmap.survey.cm5_server import stream_detections
    from surmap.survey.v1 import survey_pb2

    class RecordingSource:
        def __init__(self) -> None:
            self.frames: list[int] = []

        def detect_tracked(
            self, frame_id: int, rgb: NDArray[np.uint8]
        ) -> tuple[TrackedDetection, ...]:
            self.frames.append(frame_id)
            return (TrackedDetection("car", 0.8, (1.0, 2.0, 30.0, 40.0), 3, frame_id),)

    source = RecordingSource()
    requests = [
        survey_pb2.Cm5Request(config=survey_pb2.Cm5StreamConfig()),
        survey_pb2.Cm5Request(
            frame=survey_pb2.RawVideoFrame(
                frame_id=11,
                t_ns=111,
                channel=0,
                width=64,
                height=48,
                encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                data=_jpeg_bytes(),
            )
        ),
        survey_pb2.Cm5Request(
            frame=survey_pb2.RawVideoFrame(
                frame_id=11,
                t_ns=111,
                channel=1,
                width=64,
                height=48,
                encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                data=_jpeg_bytes(),
            )
        ),
        survey_pb2.Cm5Request(
            frame=survey_pb2.RawVideoFrame(
                frame_id=12,
                t_ns=222,
                channel=0,
                width=64,
                height=48,
                encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                data=_jpeg_bytes(),
            )
        ),
    ]

    async def feed() -> object:
        for request in requests:
            yield request

    responses = [response async for response in stream_detections(feed(), source)]  # type: ignore[arg-type]

    # Only channel-0 frames are analyzed, and each detection message
    # stands alone with its frame_id — nothing rides on survey frames
    assert source.frames == [11, 12]
    assert [r.detections.frame_id for r in responses] == [11, 12]
    assert responses[0].detections.detections[0].track_id == 3
    assert responses[0].detections.t_ns == 111


def test_object_point_source_lifts_box_points_to_the_map_frame() -> None:
    from surmap.survey.stereo import StereoRig

    source = CoralObjectPointSource(
        _StubSource(),
        _StubStereo(),
        StereoRig(100.0, 100.0, 50.0, 50.0, 0.1),
    )
    pair = StereoFramePair(3, 300, "l", "r", "cal", b"jpeg-left", b"jpeg-right")
    # The stub frames are not decodable images, so use real JPEG bytes
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (100, 100), (120, 120, 120)).save(buffer, format="JPEG")
    pair = StereoFramePair(3, 300, "l", "r", "cal", buffer.getvalue(), buffer.getvalue())

    (observation,) = source.points_for_pair(pair, Pose(Vec3(10.0, 0.0, 0.0)))

    assert observation.track_id == 5
    assert len(observation.points) == 3  # the (5,5,1) point projects outside the box
    assert all(point.x >= 10.0 for point in observation.points)
    assert source.points_for_pair(pair, None) == ()
