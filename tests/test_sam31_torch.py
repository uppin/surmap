"""Real SAM 3.1 video streamer tests, through a fake vendor model.

`Sam31VideoStreamer` drives Meta's multiplex model (init state over
a frame directory, prompt once, propagate) and converts each frame's
`out_*` arrays into `SamDetection`s. The model seam is faked here, so
no torch, GPU or gated checkpoint is needed; production is the same
streamer over `sam3.model_builder.build_sam3_predictor(...).model`.
"""

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from surmap.survey.sam3 import Sam3Unavailable
from surmap.survey.sam3_torch import Sam31VideoStreamer, sam31_video_streamer


class FakeModel:
    """Vendor multiplex-model double: records calls, yields two frames."""

    def __init__(self) -> None:
        self.prompts: list[tuple[int, str | None]] = []
        self.frame_files: list[str] = []
        self.propagated_from: list[int] = []
        self.sessions = 0
        self._num_frames = 0

    def init_state(
        self,
        resource_path: str,
        async_loading_frames: bool = False,
        offload_video_to_cpu: bool = False,
    ) -> object:
        self.sessions += 1
        self.frame_files = sorted(path.name for path in Path(resource_path).iterdir())
        self._num_frames = len(self.frame_files)
        return {"resource": resource_path}

    def add_prompt(
        self, inference_state: object, frame_idx: int, text_str: str | None = None
    ) -> None:
        self.prompts.append((frame_idx, text_str))

    def propagate_in_video(
        self,
        inference_state: object,
        start_frame_idx: int = 0,
        reverse: bool = False,
    ) -> Iterator[tuple[int, dict[str, Any]]]:
        self.propagated_from.append(start_frame_idx)
        mask = np.zeros((48, 64), dtype=bool)
        mask[10:30, 20:50] = True
        for frame_index in range(self._num_frames):
            yield (
                frame_index,
                {
                    "out_obj_ids": np.array([7]),
                    "out_probs": np.array([0.87]),
                    # Normalised xyxy, as the multiplex model emits them:
                    # pixel (20, 10)-(50, 30) on a 64x48 frame.
                    "out_boxes_xywh": np.array([[20 / 64, 10 / 48, 50 / 64, 30 / 48]]),
                    "out_binary_masks": np.array([mask]),
                },
            )


def _frame_files(tmp_path: Path) -> list[Path]:
    paths = []
    for index in range(2):
        path = tmp_path / f"source-{index}.jpg"
        path.write_bytes(b"jpeg")
        paths.append(path)
    return paths


def test_the_streamer_prompts_once_and_converts_each_frame(tmp_path: Path) -> None:
    # Given a SAM 3.1 streamer over the fake model, prompted "car"
    model = FakeModel()
    streamer = Sam31VideoStreamer(model, prompt="car")

    # When the video is streamed
    frames = list(streamer.stream(_frame_files(tmp_path)))

    # Then the model was prompted once at frame 0 over ordered frame
    # files and propagated forward from frame 0
    assert model.prompts == [(0, "car")]
    assert model.frame_files == ["000000.jpg", "000001.jpg"]
    assert model.propagated_from == [0]

    # And each frame's arrays became detections: SAM's id is the track
    # id, the normalised box was scaled to pixels, the mask a polygon
    assert [index for index, _ in frames] == [0, 1]
    (detection,) = frames[0][1]
    assert detection.label == "car"
    assert detection.track_id == 7
    assert detection.score == pytest.approx(0.87)
    assert detection.box_xyxy == (20.0, 10.0, 50.0, 30.0)
    assert (20.0, 10.0) in detection.mask_polygon


def test_prompting_runs_inside_the_autocast_context(tmp_path: Path) -> None:
    # Given a streamer whose autocast records entry, and a model that
    # records prompting (bf16 weights fail outside autocast on a
    # worker thread — the dtype mismatch this regressed into)
    events: list[str] = []

    from contextlib import contextmanager

    @contextmanager
    def autocast() -> Iterator[None]:
        events.append("autocast-enter")
        yield
        events.append("autocast-exit")

    class PromptRecorder(FakeModel):
        def add_prompt(
            self, inference_state: object, frame_idx: int, text_str: str | None = None
        ) -> None:
            events.append("add_prompt")
            super().add_prompt(inference_state, frame_idx, text_str)

    streamer = Sam31VideoStreamer(PromptRecorder(), prompt="car", autocast=autocast)

    # When the video is streamed
    list(streamer.stream(_frame_files(tmp_path)))

    # Then the prompt was issued while autocast was active
    assert (
        events.index("autocast-enter") < events.index("add_prompt") < events.index("autocast-exit")
    )


def test_long_videos_propagate_in_windows_with_global_indices(tmp_path: Path) -> None:
    # Given a streamer windowed to one frame per session
    model = FakeModel()
    streamer = Sam31VideoStreamer(model, prompt="car", chunk_frames=1)

    # When a two-frame video is streamed
    frames = list(streamer.stream(_frame_files(tmp_path)))

    # Then each frame ran in its own session, with global indices kept
    assert model.sessions == 2
    assert [index for index, _ in frames] == [0, 1]


class FakeProcessor:
    """Vendor image-processor double: one bright-box detection per frame."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def set_image(self, image: object, state: object = None) -> dict[str, Any]:
        return {"image": image}

    def set_text_prompt(self, prompt: str, state: dict[str, Any]) -> dict[str, Any]:
        self.prompts.append(prompt)
        mask = np.zeros((256, 256), dtype=bool)
        mask[20:60, 30:90] = True
        return {
            **state,
            "masks": np.stack([mask]),
            "boxes": np.array([[30.0, 20.0, 90.0, 60.0]]),
            "scores": np.array([0.87]),
        }


async def test_the_torch_detector_segments_a_frame_with_its_prompt() -> None:
    from contextlib import contextmanager

    from PIL import Image

    from surmap.survey.sam import RawFrame
    from surmap.survey.sam3_torch import Sam31TorchDetector

    # Given a SAM 3.1 image processor and one frame to segment, with
    # the bf16 autocast context the vendor weights require
    processor = FakeProcessor()
    autocast_on: list[bool] = []

    @contextmanager
    def autocast() -> Iterator[None]:
        autocast_on.append(True)
        yield

    detector = Sam31TorchDetector(processor, prompt="car", autocast=autocast)
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), (10, 10, 10)).save(buffer, format="JPEG")
    frame = RawFrame(1, 100, 0, 256, 256, "mjpeg", buffer.getvalue())

    # When the station detector segments the frame
    (detection,) = await detector.detect(frame)

    # Then SAM was prompted with the concept under autocast, and the
    # box came back in frame pixels
    assert autocast_on == [True]
    assert processor.prompts == ["car"]
    assert detection.label == "car"
    assert detection.score == pytest.approx(0.87)
    assert detection.box_xyxy == (30.0, 20.0, 90.0, 60.0)
    assert detection.mask_polygon


async def test_the_torch_detector_scales_its_mask_polygon_to_frame_pixels() -> None:
    from PIL import Image

    from surmap.survey.sam import RawFrame
    from surmap.survey.sam3_torch import Sam31TorchDetector

    # Given a frame larger than the model's mask grid (the fake
    # processor's masks are 256x256 with the vendor's leading
    # channel dim; this frame is 620x188)
    class ChannelFirstProcessor(FakeProcessor):
        def set_text_prompt(self, prompt: str, state: dict[str, Any]) -> dict[str, Any]:
            result = super().set_text_prompt(prompt, state)
            result["masks"] = result["masks"][:, None, :, :]
            return result

    processor = ChannelFirstProcessor()
    detector = Sam31TorchDetector(processor, prompt="car")
    buffer = io.BytesIO()
    Image.new("RGB", (620, 188), (10, 10, 10)).save(buffer, format="JPEG")
    frame = RawFrame(1, 100, 0, 620, 188, "mjpeg", buffer.getvalue())

    # When the frame is segmented
    (detection,) = await detector.detect(frame)

    # Then the mask polygon is in frame pixels, around the box —
    # the fake mask spans rows 20-59, columns 30-89 of its grid
    xs = [point[0] for point in detection.mask_polygon]
    ys = [point[1] for point in detection.mask_polygon]
    assert min(xs) == pytest.approx(30 * 620 / 256)
    assert max(xs) == pytest.approx(89 * 620 / 256)
    assert min(ys) == pytest.approx(20 * 188 / 256)
    assert max(ys) == pytest.approx(59 * 188 / 256)


async def test_the_torch_detectors_prompt_can_be_reset_per_stream() -> None:
    from PIL import Image

    from surmap.survey.sam import RawFrame
    from surmap.survey.sam3_torch import Sam31TorchDetector

    # Given a detector built with one concept
    processor = FakeProcessor()
    detector = Sam31TorchDetector(processor, prompt="object")
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), (10, 10, 10)).save(buffer, format="JPEG")
    frame = RawFrame(1, 100, 0, 256, 256, "mjpeg", buffer.getvalue())

    # When a stream resets the concept and a frame is segmented
    detector.set_prompt("car")
    (detection,) = await detector.detect(frame)

    # Then SAM was prompted with the stream's concept and labels so
    assert processor.prompts == ["car"]
    assert detection.label == "car"


def test_a_missing_sam3_stack_fails_by_name() -> None:
    # Given / When the real model is built where the sam3 stack
    # cannot be imported, Then it names the install that provides it
    with pytest.raises(Sam3Unavailable, match="sam3"):
        sam31_video_streamer("facebook/sam3.1", device="cuda:0", _importer=_missing)


class FakeBFloatTensor:
    """A bf16 vendor tensor double: NumPy refuses it until floated."""

    def __init__(self, array: np.ndarray, dtype: str = "bfloat16") -> None:
        self._array = array
        self.dtype = dtype

    def detach(self) -> "FakeBFloatTensor":
        return self

    def cpu(self) -> "FakeBFloatTensor":
        return self

    def float(self) -> "FakeBFloatTensor":
        return FakeBFloatTensor(self._array.astype(np.float32), "float32")

    def numpy(self) -> np.ndarray:
        if self.dtype == "bfloat16":
            raise TypeError("Got unsupported ScalarType BFloat16")
        return self._array


async def test_the_torch_detector_converts_bf16_outputs_to_detections() -> None:
    from PIL import Image

    from surmap.survey.sam import RawFrame
    from surmap.survey.sam3_torch import Sam31TorchDetector

    # Given a processor whose scores come back as bf16 tensors
    class BFloatProcessor(FakeProcessor):
        def set_text_prompt(self, prompt: str, state: dict[str, Any]) -> dict[str, Any]:
            result = super().set_text_prompt(prompt, state)
            result["scores"] = FakeBFloatTensor(np.array([0.87], dtype=np.float32))
            result["boxes"] = FakeBFloatTensor(
                np.array([[30.0, 20.0, 90.0, 60.0]], dtype=np.float32)
            )
            return result

    detector = Sam31TorchDetector(BFloatProcessor(), prompt="car")
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), (10, 10, 10)).save(buffer, format="JPEG")
    frame = RawFrame(1, 100, 0, 256, 256, "mjpeg", buffer.getvalue())

    # When the frame is segmented
    (detection,) = await detector.detect(frame)

    # Then the bf16 outputs became a normal detection
    assert detection.score == pytest.approx(0.87)
    assert detection.box_xyxy == (30.0, 20.0, 90.0, 60.0)


def test_the_torch_detector_factory_builds_the_image_model_on_cuda(tmp_path: Path) -> None:
    from surmap.survey.sam3_torch import Sam31TorchDetector, sam31_torch_detector

    # Given a local checkpoint and a fake torch/sam3 stack
    checkpoint = tmp_path / "sam3.1_multiplex.pt"
    checkpoint.write_bytes(b"fake")
    built: dict[str, Any] = {}

    class FakeCuda:
        def is_available(self) -> bool:
            return True

        def set_device(self, index: int) -> None:
            built["set_device"] = index

    class FakeBuilder:
        def build_sam3_image_model(self, **kwargs: Any) -> object:
            built.update(kwargs)
            return object()

    class FakeProcessorModule:
        class Sam3Processor:
            def __init__(self, model: object, device: str = "cpu") -> None:
                built["processor_device"] = device

    modules: dict[str, Any] = {
        "torch": type("FakeTorch", (), {"cuda": FakeCuda()})(),
        "sam3.model_builder": FakeBuilder(),
        "sam3.model.sam3_image_processor": FakeProcessorModule(),
    }

    # When the station detector is built for cuda:0
    detector = sam31_torch_detector(str(checkpoint), device="cuda:0", _importer=modules.__getitem__)

    # Then the image model is built with the exact device string its
    # builder moves weights for, on the GPU the service asked for
    assert isinstance(detector, Sam31TorchDetector)
    assert built["device"] == "cuda"
    assert built["set_device"] == 0
    assert built["checkpoint_path"] == str(checkpoint)


def test_the_torch_detector_factory_names_a_missing_sam3_stack() -> None:
    from surmap.survey.sam3_torch import sam31_torch_detector

    # Given / When the station detector is built without the sam3 stack
    # Then it fails by name, with the install that provides it
    with pytest.raises(Sam3Unavailable, match="sam3"):
        sam31_torch_detector("facebook/sam3.1", device="cuda:0", _importer=_missing)


def _missing(name: str) -> object:
    raise ImportError(f"no module named {name!r}")


def test_a_runs_prompt_replaces_the_configured_one(tmp_path: Path) -> None:
    # Given a streamer configured for "car"
    model = FakeModel()
    streamer = Sam31VideoStreamer(model, prompt="car")

    # When a video is streamed prompted "person"
    frames = list(streamer.stream(_frame_files(tmp_path), prompt="person"))

    # Then SAM was prompted for people and labels its detections so
    assert model.prompts == [(0, "person")]
    assert {detection.label for _, detections in frames for detection in detections} == {"person"}
