"""SAM 2.1 box-prompted segmentation, behind an ONNX Runtime seam.

SAM 2.1 (`facebook/sam2.1-hiera-small`, Apache-2.0, not gated) stands
in for SAM 3 until access to the gated SAM 3 checkpoints is granted
(`docs/architecture.md` §3.1 lists SAM 2 as the fallback). It has no
text prompts, so it is steered by boxes: the on-board Coral detector's
tracked boxes are the prompts and each mask inherits its box's label
and track id.

Model contract (two graphs, exported by `scripts/fetch_sam2_model.py`
into a directory with a `manifest.json`):

- encoder: `pixel_values` float32 [1, 3, S, S] (resized to S×S,
  /255, mean/std normalised) → the image embeddings (three tensors
  for SAM 2.1, passed to the decoder unchanged);
- decoder: those embeddings plus `boxes` float32 [1, N, 4] in input
  pixels → `masks` float32 [1, N, 1, M, M] logits and `iou_scores`
  float32 [1, N, 1].

The encoder dominates the cost, so a frame with no prompts never
runs it. On a Mac it runs on the GPU (Metal) through ONNX Runtime's
CoreML provider: about 0.34 s per frame against about 1 s on the CPU,
same outputs (max diff 3e-5). CoreML compiles the graph on first
load (about 45 s) and caches it next to the model (about 12 s after
that). The decoder stays on the CPU: CoreML cannot compile its
dynamic box count, and it costs only about 80 ms.
"""

from __future__ import annotations

import importlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.survey.sam import SamDetection
from surmap.survey.sam3 import mask_outline

MODEL_DIR_ENV = "SURMAP_SAM2_MODEL_DIR"
DEVICES = ("auto", "cpu", "cuda", "coreml")

_CPU = "CPUExecutionProvider"
_CUDA = "CUDAExecutionProvider"
_COREML = "CoreMLExecutionProvider"

Provider = str | tuple[str, dict[str, str]]


def default_sam2_model_dir() -> Path:
    """Where `scripts/fetch_sam2_model.py` puts the exported model."""
    configured = os.environ.get(MODEL_DIR_ENV, "").strip()
    if configured:
        return Path(configured)
    return Path.home() / ".cache" / "surmap" / "sam2" / "sam2.1-hiera-small"


class Sam2Unavailable(RuntimeError):
    """Raised when the SAM 2.1 runtime or model cannot be used."""


@dataclass(frozen=True)
class BoxPrompt:
    """One box to segment, in frame pixels, with what it is."""

    label: str
    score: float
    box_xyxy: tuple[float, float, float, float]
    track_id: int | None = None


@dataclass(frozen=True)
class Sam2Segment:
    """One segmented prompt: the detection plus its frame-sized mask."""

    detection: SamDetection
    mask: NDArray[np.bool_]


class Sam2Session(Protocol):
    """One loaded model: an image encoder and a box-prompted decoder."""

    @property
    def input_size(self) -> int: ...

    @property
    def mean(self) -> tuple[float, float, float]: ...

    @property
    def std(self) -> tuple[float, float, float]: ...

    def encode(self, pixel_values: NDArray[np.float32]) -> tuple[NDArray[np.float32], ...]: ...

    def decode(
        self, embeddings: tuple[NDArray[np.float32], ...], boxes: NDArray[np.float32]
    ) -> tuple[NDArray[np.float32], NDArray[np.float32]]: ...


def encoder_providers(device: str, available: Sequence[str], *, cache_dir: Path) -> list[Provider]:
    """ONNX Runtime providers for the image encoder (the expensive graph).

    `auto` prefers CUDA, then CoreML on the GPU (Metal), then the CPU.
    """
    if device not in DEVICES:
        raise ValueError(f"unknown device: {device}")
    if device in ("cuda", "auto") and _CUDA in available:
        return [_CUDA, _CPU]
    if device == "cuda":
        raise Sam2Unavailable("CUDA execution provider is not available")
    if device in ("coreml", "auto") and _COREML in available:
        coreml = {
            "ModelFormat": "MLProgram",
            "MLComputeUnits": "CPUAndGPU",
            "ModelCacheDirectory": str(cache_dir),
        }
        return [(_COREML, coreml), _CPU]
    if device == "coreml":
        raise Sam2Unavailable("CoreML execution provider is not available (macOS only)")
    return [_CPU]


def decoder_providers(device: str, available: Sequence[str]) -> list[Provider]:
    """Providers for the box decoder: CUDA when present, never CoreML."""
    if device not in DEVICES:
        raise ValueError(f"unknown device: {device}")
    if device in ("cuda", "auto") and _CUDA in available:
        return [_CUDA, _CPU]
    return [_CPU]


def _triple(values: object, field: str) -> tuple[float, float, float]:
    if not isinstance(values, list) or len(values) != 3:
        raise Sam2Unavailable(f"SAM 2.1 manifest field {field!r} is not three numbers")
    first, second, third = (float(value) for value in values)
    return (first, second, third)


class OnnxSam2Session:
    """`Sam2Session` over ONNX Runtime (CUDA preferred when present)."""

    def __init__(self, model_dir: Path, *, device: str = "auto") -> None:
        manifest_path = model_dir / "manifest.json"
        if not manifest_path.is_file():
            raise Sam2Unavailable(
                f"no SAM 2.1 model at {model_dir}; export it with "
                "`uv run python scripts/fetch_sam2_model.py`"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise Sam2Unavailable(f"{manifest_path} is not a JSON object")
        try:
            ort = importlib.import_module("onnxruntime")
        except ImportError as exc:
            raise Sam2Unavailable("onnxruntime is not importable") from exc
        available = cast(list[str], ort.get_available_providers())
        cache_dir = model_dir / "coreml-cache"
        cache_dir.mkdir(exist_ok=True)
        self._input_size = int(manifest["input_size"])
        self._mean = _triple(manifest.get("mean"), "mean")
        self._std = _triple(manifest.get("std"), "std")
        self._encoder: Any = ort.InferenceSession(
            str(model_dir / str(manifest["encoder"])),
            providers=encoder_providers(device, available, cache_dir=cache_dir),
        )
        self._decoder: Any = ort.InferenceSession(
            str(model_dir / str(manifest["decoder"])),
            providers=decoder_providers(device, available),
        )
        self.provider = str(self._encoder.get_providers()[0])

    @property
    def input_size(self) -> int:
        return self._input_size

    @property
    def mean(self) -> tuple[float, float, float]:
        return self._mean

    @property
    def std(self) -> tuple[float, float, float]:
        return self._std

    def encode(self, pixel_values: NDArray[np.float32]) -> tuple[NDArray[np.float32], ...]:
        name = self._encoder.get_inputs()[0].name
        return tuple(cast(list[NDArray[np.float32]], self._encoder.run(None, {name: pixel_values})))

    def decode(
        self, embeddings: tuple[NDArray[np.float32], ...], boxes: NDArray[np.float32]
    ) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        names = [node.name for node in self._decoder.get_inputs()]
        feed = dict(zip(names[: len(embeddings)], embeddings, strict=True))
        feed[names[len(embeddings)]] = boxes
        masks, scores = cast(list[NDArray[np.float32]], self._decoder.run(None, feed))
        return masks, scores


class Sam2BoxSegmenter:
    """Frame + box prompts in, one masked `Sam2Segment` per found prompt."""

    def __init__(
        self,
        session: Sam2Session,
        *,
        mask_threshold: float = 0.0,
        min_area_fraction: float = 0.0005,
    ) -> None:
        self._session = session
        self._mask_threshold = mask_threshold
        self._min_area = min_area_fraction

    def _pixel_values(self, rgb: NDArray[np.uint8]) -> NDArray[np.float32]:
        size = self._session.input_size
        resized = Image.fromarray(rgb).resize((size, size), Image.Resampling.BILINEAR)
        scaled = np.asarray(resized, dtype=np.float32) / 255.0
        mean = np.asarray(self._session.mean, dtype=np.float32)
        std = np.asarray(self._session.std, dtype=np.float32)
        normalised = (scaled - mean) / std
        return np.expand_dims(normalised.transpose(2, 0, 1), 0).astype(np.float32)

    def segment(
        self, rgb: NDArray[np.uint8], prompts: Sequence[BoxPrompt]
    ) -> tuple[Sam2Segment, ...]:
        if not prompts:
            return ()
        frame_h, frame_w = rgb.shape[:2]
        size = self._session.input_size
        to_input = np.asarray(
            [size / frame_w, size / frame_h, size / frame_w, size / frame_h], dtype=np.float32
        )
        boxes = np.asarray([[prompt.box_xyxy for prompt in prompts]], dtype=np.float32) * to_input
        masks, scores = self._session.decode(self._session.encode(self._pixel_values(rgb)), boxes)
        segments: list[Sam2Segment] = []
        for index, prompt in enumerate(prompts):
            logits = Image.fromarray(masks[0, index, 0].astype(np.float32), mode="F")
            mask = np.asarray(logits.resize((frame_w, frame_h), Image.Resampling.BILINEAR))
            mask = mask > self._mask_threshold
            if float(mask.mean()) < self._min_area:
                continue
            rows = np.nonzero(mask.any(axis=1))[0]
            columns = np.nonzero(mask.any(axis=0))[0]
            segments.append(
                Sam2Segment(
                    SamDetection(
                        label=prompt.label,
                        score=float(scores[0, index, 0]),
                        box_xyxy=(
                            float(columns[0]),
                            float(rows[0]),
                            float(columns[-1] + 1),
                            float(rows[-1] + 1),
                        ),
                        mask_polygon=mask_outline(mask, 1.0, 1.0),
                        track_id=prompt.track_id,
                    ),
                    mask,
                )
            )
        return tuple(segments)


def sam2_segmenter(model_dir: Path, *, device: str = "auto") -> Sam2BoxSegmenter:
    """A `Sam2BoxSegmenter` over the exported model in `model_dir`."""
    return Sam2BoxSegmenter(OnnxSam2Session(model_dir, device=device))
