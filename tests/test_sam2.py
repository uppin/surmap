"""SAM 2.1 box-prompted segmenter tests over a fake session.

The fake stands in at the `Sam2Session` seam (the ONNX encoder and
decoder graphs): it answers each prompt box with positive mask logits
inside that box, so the segmenter's pre-processing (box scaling into
the model input) and post-processing (mask back to frame pixels,
label carried from the prompt) are exercised exactly. A real-model
check runs only when an exported model is present.
"""

import os
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.survey.sam2 import (
    BoxPrompt,
    OnnxSam2Session,
    Sam2BoxSegmenter,
    Sam2Unavailable,
    decoder_providers,
    default_sam2_model_dir,
    encoder_providers,
)

FRAME_WIDTH = 32
FRAME_HEIGHT = 16


class BoxMaskSession:
    """`Sam2Session` fake: positive logits inside each prompted box."""

    input_size = 64
    mask_size = 16
    mean = (0.0, 0.0, 0.0)
    std = (1.0, 1.0, 1.0)

    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty
        self.encodes = 0
        self.boxes: list[list[list[float]]] = []

    def encode(self, pixel_values: NDArray[np.float32]) -> tuple[NDArray[np.float32], ...]:
        self.encodes += 1
        return (np.zeros((1, 1), dtype=np.float32),)

    def decode(
        self, embeddings: tuple[NDArray[np.float32], ...], boxes: NDArray[np.float32]
    ) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        self.boxes.append(boxes.tolist()[0])
        count = boxes.shape[1]
        masks = np.full((1, count, 1, self.mask_size, self.mask_size), -10.0, dtype=np.float32)
        scale = self.mask_size / self.input_size
        for index in range(count):
            x0, y0, x1, y1 = (int(round(value * scale)) for value in boxes[0, index])
            if not self.empty:
                masks[0, index, 0, y0:y1, x0:x1] = 10.0
        return masks, np.full((1, count, 1), 0.9, dtype=np.float32)


def a_frame() -> NDArray[np.uint8]:
    return np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), 120, dtype=np.uint8)


def a_chair_prompt() -> BoxPrompt:
    return BoxPrompt(label="chair", score=0.8, box_xyxy=(8.0, 4.0, 24.0, 12.0), track_id=7)


def test_a_box_prompt_becomes_a_mask_inside_that_box() -> None:
    # Given a segmenter whose model masks exactly the prompted box
    segmenter = Sam2BoxSegmenter(BoxMaskSession())

    # When a frame is segmented with one chair prompt
    (segment,) = segmenter.segment(a_frame(), (a_chair_prompt(),))

    # Then the frame-sized mask covers the box and nothing outside it
    assert segment.mask.shape == (FRAME_HEIGHT, FRAME_WIDTH)
    assert segment.mask[8, 16]
    assert not segment.mask[1, 1]
    assert not segment.mask[14, 30]


def test_the_mask_inherits_the_prompt_label_and_track() -> None:
    # Given a segmenter over the box-masking model
    segmenter = Sam2BoxSegmenter(BoxMaskSession())

    # When a frame is segmented with a tracked chair prompt
    (segment,) = segmenter.segment(a_frame(), (a_chair_prompt(),))

    # Then the detection is the chair, with its track and an outline
    assert segment.detection.label == "chair"
    assert segment.detection.track_id == 7
    assert segment.detection.score == pytest.approx(0.9)
    assert len(segment.detection.mask_polygon) >= 3


def test_prompt_boxes_are_scaled_into_the_model_input_space() -> None:
    # Given a 64 px model input for a 32x16 frame (x2 wide, x4 tall)
    session = BoxMaskSession()
    segmenter = Sam2BoxSegmenter(session)

    # When the chair box (8, 4)-(24, 12) is prompted
    segmenter.segment(a_frame(), (a_chair_prompt(),))

    # Then the decoder sees the box in input pixels
    assert session.boxes == [[[16.0, 16.0, 48.0, 48.0]]]


def test_a_frame_without_prompts_never_runs_the_encoder() -> None:
    # Given a segmenter
    session = BoxMaskSession()
    segmenter = Sam2BoxSegmenter(session)

    # When a frame arrives with no Coral boxes
    segments = segmenter.segment(a_frame(), ())

    # Then nothing is segmented and the expensive encoder never ran
    assert segments == ()
    assert session.encodes == 0


def test_an_empty_mask_is_dropped() -> None:
    # Given a model that finds nothing inside the prompted box
    segmenter = Sam2BoxSegmenter(BoxMaskSession(empty=True))

    # When the frame is segmented
    segments = segmenter.segment(a_frame(), (a_chair_prompt(),))

    # Then no segment is reported for that prompt
    assert segments == ()


def test_a_missing_model_dir_says_how_to_fetch_it(tmp_path: Path) -> None:
    with pytest.raises(Sam2Unavailable, match="fetch_sam2_model"):
        OnnxSam2Session(tmp_path / "missing")


REAL_MODEL = Path(os.environ.get("SURMAP_SAM2_MODEL_DIR", "") or default_sam2_model_dir())


@pytest.mark.skipif(
    not (REAL_MODEL / "manifest.json").is_file(),
    reason="no exported SAM 2.1 model (scripts/fetch_sam2_model.py)",
)
def test_the_real_sam2_model_masks_a_bright_square_inside_its_box() -> None:
    # Given the exported SAM 2.1 model and a bright square on grey
    frame = np.full((240, 376, 3), 60, dtype=np.uint8)
    frame[80:160, 140:240] = 230
    segmenter = Sam2BoxSegmenter(OnnxSam2Session(REAL_MODEL, device="cpu"))
    prompt = BoxPrompt(label="box", score=0.9, box_xyxy=(130.0, 70.0, 250.0, 170.0), track_id=1)

    # When the square is prompted with a box around it
    (segment,) = segmenter.segment(frame, (prompt,))

    # Then the mask holds the square's centre and not the far corner
    assert segment.mask[120, 190]
    assert not segment.mask[5, 5]


CPU = "CPUExecutionProvider"
COREML = "CoreMLExecutionProvider"
CUDA = "CUDAExecutionProvider"


def test_on_a_mac_the_encoder_runs_on_the_gpu_through_coreml(tmp_path: Path) -> None:
    # Given ONNX Runtime's macOS providers
    available = [COREML, CPU]

    # When providers are chosen automatically
    providers = encoder_providers("auto", available, cache_dir=tmp_path)

    # Then the encoder asks CoreML for the GPU, caching its compiled model
    assert providers == [
        (
            COREML,
            {
                "ModelFormat": "MLProgram",
                "MLComputeUnits": "CPUAndGPU",
                "ModelCacheDirectory": str(tmp_path),
            },
        ),
        CPU,
    ]


def test_cuda_is_preferred_over_coreml_when_both_exist(tmp_path: Path) -> None:
    providers = encoder_providers("auto", [CUDA, COREML, CPU], cache_dir=tmp_path)
    assert providers == [CUDA, CPU]


def test_the_box_decoder_never_runs_on_coreml() -> None:
    # Given CoreML is available (it cannot compile the dynamic box count)
    available = [COREML, CPU]

    # When decoder providers are chosen automatically
    providers = decoder_providers("auto", available)

    # Then the decoder stays on the CPU
    assert providers == [CPU]


def test_cpu_forces_the_cpu_for_both_graphs(tmp_path: Path) -> None:
    assert encoder_providers("cpu", [CUDA, COREML, CPU], cache_dir=tmp_path) == [CPU]
    assert decoder_providers("cpu", [CUDA, COREML, CPU]) == [CPU]


def test_asking_for_coreml_without_it_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(Sam2Unavailable, match="CoreML"):
        encoder_providers("coreml", [CPU], cache_dir=tmp_path)
