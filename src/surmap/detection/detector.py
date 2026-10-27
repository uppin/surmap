"""Coral Edge TPU object detector, behind a lazy TFLite boundary.

The detector is Google's EfficientDet-Lite0 INT8 (COCO) — the
Coral-native fallback recorded in docs/coral-edge-tpu-model-spike.md
after the Meta-model spike found no Meta(-family) model that runs
compiled on the Edge TPU. Two pinned artifacts of the same network
exist (tooling: `scripts/fetch_coral_model.py`):

- `efficientdet_lite0_320_ptq_edgetpu.tflite` — Edge-TPU-compiled,
  for CM5 hardware with the Edge TPU delegate (fits the ~8 MB
  parameter cache at 5.96 MB);
- `efficientdet_lite0_320_ptq.tflite` — the CPU twin, for CI/local
  proof on machines with no Coral board.

The TFLite runtime (`ai-edge-litert`, falling back to
`tflite-runtime`) is a declared project dependency but is imported
lazily here, so importing this module never requires it and unit
tests can inject a fake interpreter factory.
"""

from __future__ import annotations

import importlib
import io
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.survey.stereo import FrameImage
from surmap.types import Detection


class DetectorUnavailable(RuntimeError):
    """Raised when no usable TFLite runtime/model combination exists."""


class _Interpreter(Protocol):
    def allocate_tensors(self) -> None: ...

    def get_input_details(self) -> list[dict[str, Any]]: ...

    def get_output_details(self) -> list[dict[str, Any]]: ...

    def set_tensor(self, index: int, value: NDArray[np.uint8]) -> None: ...

    def invoke(self) -> None: ...

    def get_tensor(self, index: int) -> NDArray[Any]: ...


InterpreterFactory = Any  # Callable[..., _Interpreter]; kept loose for fakes


def decode_rgb(frame: FrameImage) -> NDArray[np.uint8]:
    """Decode one streamed frame to an HxWx3 uint8 RGB array."""
    if frame.encoding == "raw_rgb":
        expected = frame.width * frame.height * 3
        if len(frame.data) != expected:
            raise ValueError(f"raw_rgb frame has {len(frame.data)} bytes, expected {expected}")
        return (
            np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 3).copy()
        )
    try:
        with Image.open(io.BytesIO(frame.data)) as image:
            return np.asarray(image.convert("RGB"), dtype=np.uint8)
    except Exception as exc:
        raise ValueError(f"undecodable frame: {exc}") from exc


def _load_interpreter_class() -> Any:
    for module_name in ("ai_edge_litert.interpreter", "tflite_runtime.interpreter"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        return cast(Any, module.Interpreter)
    raise DetectorUnavailable(
        "no TFLite runtime is importable (expected ai-edge-litert or tflite-runtime); "
        "the detector cannot run without one"
    )


class CoralDetector:
    """EfficientDet-Lite0 INT8 detector (CPU or Edge TPU delegate)."""

    def __init__(
        self,
        model_path: Path,
        labels_path: Path,
        *,
        score_threshold: float = 0.3,
        max_detections: int = 10,
        interpreter_factory: InterpreterFactory = None,
        edgetpu_delegate: str | None = None,
    ) -> None:
        if not model_path.is_file():
            raise DetectorUnavailable(
                f"detection model not found at {model_path}; run "
                "`uv run python scripts/fetch_coral_model.py`"
            )
        self._model_path = model_path
        self._labels = labels_path.read_text(encoding="utf-8").splitlines()
        self._score_threshold = score_threshold
        self._max_detections = max_detections
        self._factory = interpreter_factory
        self._delegate = edgetpu_delegate
        self._interpreter: _Interpreter | None = None

    @property
    def model_id(self) -> str:
        return self._model_path.name

    def _ensure_interpreter(self) -> _Interpreter:
        if self._interpreter is not None:
            return self._interpreter
        if self._factory is not None:
            interpreter = cast(_Interpreter, self._factory(model_path=str(self._model_path)))
        else:
            interpreter_class = _load_interpreter_class()
            experimental_delegates = None
            if self._delegate:
                module = importlib.import_module("ai_edge_litert.interpreter")
                experimental_delegates = [module.load_delegate(self._delegate)]
            interpreter = cast(
                _Interpreter,
                interpreter_class(
                    model_path=str(self._model_path),
                    experimental_delegates=experimental_delegates,
                ),
            )
        try:
            interpreter.allocate_tensors()
        except RuntimeError as exc:
            raise DetectorUnavailable(
                f"model {self._model_path.name} cannot run on this host: {exc}. "
                "The _edgetpu artifact needs the Edge TPU delegate (Coral board); "
                "use the CPU-twin artifact on machines without one."
            ) from exc
        self._interpreter = interpreter
        return interpreter

    def detect(self, rgb: NDArray[np.uint8], frame_id: int) -> tuple[Detection, ...]:
        """Detections in `rgb` (HxWx3 uint8), boxes in its pixel space."""
        interpreter = self._ensure_interpreter()
        input_detail = interpreter.get_input_details()[0]
        _, input_h, input_w, _ = (int(value) for value in input_detail["shape"])
        height, width = rgb.shape[:2]
        with Image.fromarray(rgb) as image:
            resized = np.asarray(image.resize((input_w, input_h)), dtype=np.uint8)
        interpreter.set_tensor(input_detail["index"], np.expand_dims(resized, 0))
        try:
            interpreter.invoke()
        except RuntimeError as exc:
            raise DetectorUnavailable(f"detector invocation failed: {exc}") from exc
        outputs = interpreter.get_output_details()
        boxes = interpreter.get_tensor(outputs[0]["index"])[0]
        classes = interpreter.get_tensor(outputs[1]["index"])[0]
        scores = interpreter.get_tensor(outputs[2]["index"])[0]
        count = int(interpreter.get_tensor(outputs[3]["index"])[0])
        detections: list[Detection] = []
        for index in range(min(count, len(scores))):
            score = float(scores[index])
            if score < self._score_threshold or len(detections) >= self._max_detections:
                continue
            y_min, x_min, y_max, x_max = (float(value) for value in boxes[index])
            label_index = int(classes[index])
            label = self._labels[label_index] if 0 <= label_index < len(self._labels) else "unknown"
            detections.append(
                Detection(
                    frame_id=frame_id,
                    box_xyxy=(
                        max(0.0, x_min * width),
                        max(0.0, y_min * height),
                        min(float(width), x_max * width),
                        min(float(height), y_max * height),
                    ),
                    label=label,
                    score=score,
                    detector_model_id=self.model_id,
                )
            )
        return tuple(detections)
