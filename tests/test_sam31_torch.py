"""Real SAM 3.1 video streamer tests, through a fake vendor model.

`Sam31VideoStreamer` drives Meta's multiplex model (init state over
a frame directory, prompt once, propagate) and converts each frame's
`out_*` arrays into `SamDetection`s. The model seam is faked here, so
no torch, GPU or gated checkpoint is needed; production is the same
streamer over `sam3.model_builder.build_sam3_predictor(...).model`.
"""

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


def test_a_missing_sam3_stack_fails_by_name() -> None:
    # Given / When the real model is built where the sam3 stack
    # cannot be imported, Then it names the install that provides it
    with pytest.raises(Sam3Unavailable, match="sam3"):
        sam31_video_streamer("facebook/sam3.1", device="cuda:0", _importer=_missing)


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
