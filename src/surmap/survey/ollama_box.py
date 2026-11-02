"""Local vision-model detection behind the segmentation seam, via Ollama.

A vision-language model cannot emit SAM mask polygons, so this adapter
asks the local model for bounding boxes in 0-1000 coordinates and
carries each box as its rectangle `mask_polygon` in the same
`SamDetection` contract. That mask is deliberately coarser than a SAM
mask: `points_in_mask` claims every cloud point inside the rectangle.
Scores are `None` — the local model reports no calibrated confidence.
Tests substitute a recording transport; no socket is opened under test.
"""

from __future__ import annotations

import io
import json

from PIL import Image

from surmap.labelling.ollama import (
    OllamaError,
    OllamaTransport,
    UrllibOllamaTransport,
    chat_body,
    chat_content,
    ollama_chat_url,
    ollama_model,
)
from surmap.survey.sam import RawFrame, SamDetection


class OllamaBoxDetector:
    """Box detections for one noun prompt, from the local model."""

    def __init__(
        self,
        *,
        prompt: str = "person",
        model: str | None = None,
        transport: OllamaTransport | None = None,
        base_url: str | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        self._prompt = prompt
        self._model = ollama_model(model)
        self._url = ollama_chat_url(base_url)
        self._transport = (
            transport if transport is not None else UrllibOllamaTransport(timeout_s=timeout_s)
        )

    @property
    def model_id(self) -> str:
        return f"ollama:{self._model}"

    def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        """Boxes for the prompt noun in one frame, as rectangle-mask detections."""
        payload = self._transport.post_json(
            self._url,
            chat_body(self._model, _box_prompt(self._prompt), _frame_image(frame)),
        )
        return _parse_boxes(chat_content(payload), frame, self._prompt)


def _box_prompt(prompt: str) -> str:
    noun = " ".join(prompt.split()) or "person"
    return (
        f"List every {noun} visible in this image. Reply ONLY with a JSON array "
        'of boxes in 0-1000 coordinates: [{"x_min": 0, "y_min": 0, "x_max": 0, '
        '"y_max": 0}]. If none is visible, reply [].'
    )


def _frame_image(frame: RawFrame) -> bytes:
    if frame.encoding == "raw_rgb":
        out = io.BytesIO()
        Image.frombytes("RGB", (frame.width, frame.height), frame.data).save(out, format="PNG")
        return out.getvalue()
    if frame.encoding in ("jpeg", "mjpeg", "png"):
        return frame.data
    raise OllamaError(f"Ollama detector cannot read frame encoding {frame.encoding!r}")


def _parse_boxes(text: str, frame: RawFrame, prompt: str) -> tuple[SamDetection, ...]:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        raise OllamaError("Ollama box reply had no JSON array")
    try:
        decoded: object = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OllamaError("Ollama box reply was not valid JSON") from exc
    if not isinstance(decoded, list):
        raise OllamaError("Ollama box reply was not a JSON array")
    found: list[SamDetection] = []
    for item in decoded:
        box = _one_box(item, frame, prompt)
        if box is not None:
            found.append(box)
    return tuple(found)


def _one_box(item: object, frame: RawFrame, prompt: str) -> SamDetection | None:
    if not isinstance(item, dict):
        return None
    values: list[float] = []
    for key in ("x_min", "y_min", "x_max", "y_max"):
        value = item.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        values.append(float(value))
    x0 = min(max(values[0], 0.0), 1000.0) / 1000.0 * frame.width
    y0 = min(max(values[1], 0.0), 1000.0) / 1000.0 * frame.height
    x1 = min(max(values[2], 0.0), 1000.0) / 1000.0 * frame.width
    y1 = min(max(values[3], 0.0), 1000.0) / 1000.0 * frame.height
    if x1 <= x0 or y1 <= y0:
        return None
    label = item.get("label")
    return SamDetection(
        label=label if isinstance(label, str) and label.strip() else prompt,
        score=None,
        box_xyxy=(x0, y0, x1, y1),
        mask_polygon=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
        track_id=None,
    )
