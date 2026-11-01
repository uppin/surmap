"""SAM 3.1 on a Modal GPU, from the PyTorch checkpoint.

The station posts JPEG or PNG bytes and a text prompt to
``MODAL_SAM_URL``. The remote app ``surmap.survey.modal_sam_app``
loads ``facebook/sam3.1`` (``sam3.1_multiplex.pt``) with the official
``sam3`` image builder and returns boxes, polygons, scores, and its
own GPU seconds. CI never imports ``modal``.

Deploy, stop, the Hugging Face secret, and the Muse shared endpoint
are in ``docs/modal.md``.

    uv run --with modal modal deploy src/surmap/survey/modal_sam_app.py
    uv run --with modal modal app stop surmap-sam

The default GPU is an L4 (24 GB). A T4's 16 GB does not leave room
for that checkpoint plus activations. ``before_call``, ``on_usage``,
and ``on_gpu_seconds`` accept a plain callback or a
``surmap.usage.UsageLedger`` without importing it.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.survey.sam import RawFrame, SamDetection
from surmap.survey.sam3 import Sam3Unavailable, mask_outline

APP_NAME = "surmap-sam"
DEFAULT_GPU = "L4"
DEFAULT_PROMPT = "person"
CHECK_IMAGE = "tests/fixtures/modal_sam/person.jpg"

UsageHook = Callable[[str, str, int, int, int | None], None]
GpuSecondsHook = Callable[[float], None]
BeforeCall = Callable[[str], None]
Poster = Callable[[str, bytes], bytes]


class _LedgerCheck(Protocol):
    """The ``check`` method on ``surmap.usage.UsageLedger``."""

    def check(self, provider: str) -> None: ...


@dataclass(frozen=True)
class _CreditUse:
    """Attribute-compatible with ``surmap.usage.UsageRecord``. Not imported."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None
    t_unix: float


def resolve_modal_url(url: str | None) -> str:
    """Return a non-blank URL, or raise before any network call."""
    chosen = os.environ.get("MODAL_SAM_URL") if url is None else url
    if chosen is None or not chosen.strip():
        raise Sam3Unavailable("MODAL_SAM_URL is not set; refusing to call Modal before any request")
    return chosen.strip()


def usage_model_name(model: str | None) -> str:
    """Label recorded with usage: explicit override, else ``surmap-sam/<gpu>``."""
    if model is not None and model.strip():
        return model.strip()
    explicit = os.environ.get("MODAL_SAM_MODEL", "").strip()
    if explicit:
        return explicit
    gpu = os.environ.get("SURMAP_MODAL_GPU", DEFAULT_GPU)
    return f"{APP_NAME}/{gpu}"


def resolve_prompt(label: str) -> str:
    """``MODAL_SAM_PROMPT`` wins, otherwise the station label, else ``person``."""
    override = os.environ.get("MODAL_SAM_PROMPT", "").strip()
    if override:
        return override
    if label.strip():
        return label.strip()
    return DEFAULT_PROMPT


def encode_image_request(image: bytes, *, prompt: str, media_type: str) -> bytes:
    """JSON body: one image and the text prompt."""
    payload = {
        "prompt": prompt,
        "media_type": media_type,
        "image_b64": base64.b64encode(image).decode("ascii"),
    }
    return json.dumps(payload).encode("utf-8")


def pack_detections(
    prompt: str,
    masks: NDArray[np.float32] | NDArray[np.bool_],
    boxes: NDArray[np.float32],
    scores: NDArray[np.float32],
    *,
    image_width: int,
    image_height: int,
    inference_seconds: float,
) -> dict[str, Any]:
    """Boxes and mask outlines in the image's pixel frame, plus GPU seconds."""
    mask_stack = np.asarray(masks)
    if mask_stack.ndim == 4 and mask_stack.shape[1] == 1:
        mask_stack = mask_stack[:, 0]
    if mask_stack.ndim == 2:
        mask_stack = mask_stack[None, ...]
    box_stack = np.asarray(boxes, dtype=np.float32).reshape(-1, 4)
    score_stack = np.asarray(scores, dtype=np.float32).reshape(-1)
    count = int(score_stack.shape[0])
    mask_h = int(mask_stack.shape[1]) if mask_stack.ndim == 3 and mask_stack.shape[0] else 1
    mask_w = int(mask_stack.shape[2]) if mask_stack.ndim == 3 and mask_stack.shape[0] else 1
    scale_x = image_width / mask_w if mask_w else 1.0
    scale_y = image_height / mask_h if mask_h else 1.0
    detections: list[dict[str, Any]] = []
    for index in range(count):
        score = float(score_stack[index])
        box = box_stack[index] if index < box_stack.shape[0] else np.zeros(4, dtype=np.float32)
        polygon: tuple[tuple[float, float], ...] = ()
        if mask_stack.ndim == 3 and index < mask_stack.shape[0]:
            binary = np.asarray(mask_stack[index] >= 0.5)
            polygon = mask_outline(binary, scale_x, scale_y)
        detections.append(
            {
                "label": prompt,
                "score": score,
                "box_xyxy": [float(value) for value in box],
                "mask_polygon": [[point[0], point[1]] for point in polygon],
            }
        )
    return {
        "prompt": prompt,
        "detections": detections,
        "inference_seconds": float(inference_seconds),
    }


def parse_detections(raw: bytes) -> tuple[tuple[SamDetection, ...], float]:
    """Turn the endpoint JSON into ``SamDetection`` values and GPU seconds."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Sam3Unavailable("Modal SAM response was not JSON") from exc
    if not isinstance(payload, dict):
        raise Sam3Unavailable("Modal SAM response was not a JSON object")
    body = cast(dict[str, Any], payload)
    seconds = body.get("inference_seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, int | float):
        raise Sam3Unavailable("Modal SAM response is missing inference_seconds")
    elapsed = float(seconds)
    if elapsed < 0 or not math.isfinite(elapsed):
        raise Sam3Unavailable("Modal SAM inference_seconds is not a usable duration")
    rows = body.get("detections")
    if not isinstance(rows, list):
        raise Sam3Unavailable("Modal SAM response is missing detections")
    found: list[SamDetection] = []
    for row in rows:
        if not isinstance(row, dict):
            raise Sam3Unavailable("Modal SAM detection was not an object")
        item = cast(dict[str, Any], row)
        found.append(_detection(item))
    return tuple(found), elapsed


class _ModalRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Modal web endpoints answer long calls with repeated 303s; follow them."""

    max_repeats = 20
    max_redirections = 30


def post_json(url: str, body: bytes, *, timeout_s: float) -> bytes:
    """POST JSON with the stdlib client. No Modal SDK."""
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(_ModalRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_s) as response:
            return cast(bytes, response.read())
    except urllib.error.HTTPError as exc:
        raise Sam3Unavailable(f"Modal SAM endpoint returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise Sam3Unavailable(f"Modal SAM endpoint request failed: {exc.reason}") from exc


class ModalSamDetector:
    """``SamDetector`` that posts a frame and a text prompt to Modal."""

    def __init__(
        self,
        url: str | None = None,
        *,
        prompt: str = DEFAULT_PROMPT,
        model: str | None = None,
        on_usage: UsageHook | _LedgerCheck | None = None,
        on_gpu_seconds: GpuSecondsHook | _LedgerCheck | None = None,
        before_call: BeforeCall | _LedgerCheck | None = None,
        poster: Poster | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        self._url = resolve_modal_url(url)
        self._prompt = prompt.strip() or DEFAULT_PROMPT
        self._model = usage_model_name(model)
        self._on_usage = _bind_usage(on_usage)
        self._on_gpu_seconds = _bind_gpu(on_gpu_seconds)
        self._before_call = _bind_before(before_call)
        self._poster = poster if poster is not None else _poster(timeout_s)
        self.last_inference_seconds = 0.0

    @property
    def provider(self) -> str:
        return "modal"

    @property
    def prompt(self) -> str:
        return self._prompt

    def segment(self, image: bytes, *, media_type: str = "image/jpeg") -> tuple[SamDetection, ...]:
        """POST one image. ``before_call('modal')`` may raise to block it."""
        if self._before_call is not None:
            self._before_call("modal")
        raw = self._poster(
            self._url,
            encode_image_request(image, prompt=self._prompt, media_type=media_type),
        )
        detections, elapsed = parse_detections(raw)
        self.last_inference_seconds = elapsed
        if self._on_usage is not None:
            self._on_usage("modal", self._model, 0, 0, None)
        if self._on_gpu_seconds is not None:
            self._on_gpu_seconds(elapsed)
        return detections

    async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        """Segment one frame off the event loop."""
        image, media_type = frame_image(frame)
        return await asyncio.to_thread(self.segment, image, media_type=media_type)


def modal_sam_detector(
    *,
    label: str = DEFAULT_PROMPT,
    url: str | None = None,
    model: str | None = None,
    on_usage: UsageHook | _LedgerCheck | None = None,
    on_gpu_seconds: GpuSecondsHook | _LedgerCheck | None = None,
    before_call: BeforeCall | _LedgerCheck | None = None,
    poster: Poster | None = None,
) -> ModalSamDetector:
    """A detector whose text prompt is ``MODAL_SAM_PROMPT`` or ``label``."""
    return ModalSamDetector(
        url,
        prompt=resolve_prompt(label),
        model=model,
        on_usage=on_usage,
        on_gpu_seconds=on_gpu_seconds,
        before_call=before_call,
        poster=poster,
    )


def frame_image(frame: RawFrame) -> tuple[bytes, str]:
    """JPEG or PNG bytes for a raw frame, re-encoded when the codec is neither."""
    encoding = frame.encoding.lower()
    if encoding in {"jpeg", "jpg", "mjpeg"}:
        return frame.data, "image/jpeg"
    if encoding == "png":
        return frame.data, "image/png"
    image = Image.open(io.BytesIO(frame.data)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue(), "image/jpeg"


def run_modal_sam_check(
    image: bytes,
    *,
    url: str | None = None,
    prompt: str = DEFAULT_PROMPT,
    poster: Poster | None = None,
) -> tuple[SamDetection, ...]:
    """One live or injected call. Prints detections and GPU seconds."""
    detector = ModalSamDetector(url, prompt=prompt, poster=poster)
    started = time.perf_counter()
    detections = detector.segment(image, media_type=_media_type(image))
    elapsed = time.perf_counter() - started
    print(f"prompt: {prompt}")
    print(f"inference_seconds: {detector.last_inference_seconds:.3f}")
    print(f"round_trip_seconds: {elapsed:.3f}")
    print(f"detections: {len(detections)}")
    for detection in detections:
        x0, y0, x1, y1 = detection.box_xyxy
        print(
            f"  {detection.label} score={_score_text(detection.score)} "
            f"box=({x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}) "
            f"polygon_points={len(detection.mask_polygon)}"
        )
    return detections


def _score_text(score: float | None) -> str:
    if score is None:
        return "none"
    return f"{score:.3f}"


def _media_type(image: bytes) -> str:
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return "image/jpeg"


def _detection(item: dict[str, Any]) -> SamDetection:
    label = item.get("label")
    score = item.get("score")
    box = item.get("box_xyxy")
    polygon = item.get("mask_polygon", [])
    if not isinstance(label, str) or not label:
        raise Sam3Unavailable("Modal SAM detection is missing a label")
    if isinstance(score, bool) or not isinstance(score, int | float):
        raise Sam3Unavailable("Modal SAM detection is missing a score")
    if not isinstance(box, list) or len(box) != 4:
        raise Sam3Unavailable("Modal SAM detection box must be xyxy")
    if not isinstance(polygon, list):
        raise Sam3Unavailable("Modal SAM detection polygon must be a list")
    points: list[tuple[float, float]] = []
    for point in polygon:
        if not isinstance(point, list) or len(point) != 2:
            raise Sam3Unavailable("Modal SAM polygon point must be an x,y pair")
        points.append((float(point[0]), float(point[1])))
    xyxy = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    return SamDetection(label, float(score), xyxy, tuple(points))


def _ledger_check(hook: object) -> Callable[[str], None] | None:
    """Return ``hook.check`` when this object is a usage ledger."""
    check = getattr(hook, "check", None)
    if not callable(check):
        return None
    return cast(Callable[[str], None], check)


def _bind_before(hook: BeforeCall | _LedgerCheck | None) -> BeforeCall | None:
    if hook is None:
        return None
    check = _ledger_check(hook)
    if check is not None:
        return check
    if callable(hook):
        return hook
    raise TypeError("before_call must be a callable or a usage ledger")


def _bind_usage(hook: UsageHook | _LedgerCheck | None) -> UsageHook | None:
    if hook is None:
        return None
    if _ledger_check(hook) is not None:
        sink = cast(Callable[[_CreditUse], None], hook)

        def record(
            provider: str,
            model: str,
            input_tokens: int,
            output_tokens: int,
            reasoning_tokens: int | None,
        ) -> None:
            sink(
                _CreditUse(
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    reasoning_tokens,
                    time.time(),
                )
            )

        return record
    if callable(hook):
        return hook
    raise TypeError("on_usage must be a callable or a usage ledger")


def _bind_gpu(hook: GpuSecondsHook | _LedgerCheck | None) -> GpuSecondsHook | None:
    """A ledger is accepted and writes nothing: usage records have no GPU field."""
    if hook is None:
        return None
    if _ledger_check(hook) is not None:
        return _ignore_gpu_seconds
    if callable(hook):
        return hook
    raise TypeError("on_gpu_seconds must be a callable or a usage ledger")


def _ignore_gpu_seconds(_seconds: float) -> None:
    return None


def _poster(timeout_s: float) -> Poster:
    def send(url: str, body: bytes) -> bytes:
        return post_json(url, body, timeout_s=timeout_s)

    return send
