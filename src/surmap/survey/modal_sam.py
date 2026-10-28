"""SAM 3.1 ONNX inference on a Modal GPU.

The station posts an image tensor to ``MODAL_SAM_URL``. The remote app
in ``surmap.survey.modal_sam_app`` runs the exported ONNX model on a
GPU and returns ``masks``, ``scores``, and its own elapsed inference
time. ``Sam3Detector`` post-processes that result the same way it does
for a local CPU or CUDA session.

The checkpoint is not in git. Put it on Modal Volume ``surmap-sam3``
(mounted at ``/models/sam3.1.onnx``). CI never imports the ``modal``
package and never needs a token.

Authenticate once, in WSL, as workspace ``ginas-bb``. The token stays
in ``~/.modal.toml`` on that machine:

    uv run --with modal modal token new

Upload the license-gated export (this creates the volume if needed):

    uv run --with modal modal volume create surmap-sam3
    uv run --with modal modal volume put surmap-sam3 ./sam3.1.onnx /sam3.1.onnx

Deploy from the repo root. The default GPU is a T4. Override with
``SURMAP_MODAL_GPU`` (for example ``L4``). ``SURMAP_MODAL_TIMEOUT``
(seconds, default 300) and ``SURMAP_MODAL_SCALEDOWN_WINDOW`` (seconds,
default 60) are read at deploy time. The function sets
``max_containers=1`` and does not set ``min_containers``, so Modal
scales to zero after the idle window:

    uv run --with modal modal deploy src/surmap/survey/modal_sam_app.py

Copy the printed web URL, then start the station:

    export MODAL_SAM_URL='https://<workspace>--surmap-sam-segment.modal.run'
    python -m surmap.survey.station_main --detector sam3-modal

``MODAL_SAM_INPUT`` (default ``256x256``) must match the export's
spatial size. ``MODAL_SAM_MODEL`` overrides the usage label (default
``surmap-sam/<gpu>``).

Stop the app when the survey is finished so it cannot boot another GPU:

    uv run --with modal modal app stop surmap-sam

Spend for workspace ``ginas-bb`` is the Usage page in the Modal
dashboard (https://modal.com/settings/usage) and the ``surmap-sam``
app page listed by ``modal app list``.
"""

from __future__ import annotations

import base64
import json
import math
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from surmap.survey.sam3 import Sam3Detector, Sam3Unavailable

APP_NAME = "surmap-sam"
DEFAULT_GPU = "T4"
DEFAULT_TIMEOUT_S = 300
DEFAULT_SCALEDOWN_S = 60
MAX_CONTAINERS = 1
VOLUME_NAME = "surmap-sam3"
MODEL_DIR = "/models"
MODEL_FILENAME = "sam3.1.onnx"
REMOTE_PIP_PACKAGES = (
    "fastapi[standard]",
    "numpy>=2.0",
    "pillow>=10",
    "onnxruntime-gpu>=1.20",
)

UsageHook = Callable[[str, str, int, int, int | None], None]
GpuSecondsHook = Callable[[float], None]
BeforeCall = Callable[[str], None]
Poster = Callable[[str, bytes], bytes]


def modal_function_kwargs(environ: Mapping[str, str] | None = None) -> dict[str, str | int]:
    """GPU, timeout, idle window, and container cap for the remote function."""
    env = os.environ if environ is None else environ
    return {
        "gpu": env.get("SURMAP_MODAL_GPU", DEFAULT_GPU),
        "timeout": int(env.get("SURMAP_MODAL_TIMEOUT", str(DEFAULT_TIMEOUT_S))),
        "scaledown_window": int(env.get("SURMAP_MODAL_SCALEDOWN_WINDOW", str(DEFAULT_SCALEDOWN_S))),
        "max_containers": MAX_CONTAINERS,
    }


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


def resolve_input_size(size: tuple[int, int] | None) -> tuple[int, int]:
    """Spatial size the detector resizes to. ``MODAL_SAM_INPUT`` is ``WxH``."""
    if size is not None:
        return (int(size[0]), int(size[1]))
    raw = os.environ.get("MODAL_SAM_INPUT", "256x256").strip().lower().replace("*", "x")
    parts = raw.split("x")
    try:
        if len(parts) == 1:
            side = int(parts[0])
            return (side, side)
        if len(parts) == 2:
            return (int(parts[0]), int(parts[1]))
    except ValueError as exc:
        raise Sam3Unavailable("MODAL_SAM_INPUT must look like 256x256") from exc
    raise Sam3Unavailable("MODAL_SAM_INPUT must look like 256x256")


def encode_request(image: NDArray[np.float32]) -> bytes:
    """JSON body for one NCHW float32 tensor."""
    array = np.ascontiguousarray(image, dtype=np.float32)
    payload = {
        "shape": [int(dim) for dim in array.shape],
        "data_b64": base64.b64encode(array.tobytes()).decode("ascii"),
    }
    return json.dumps(payload).encode("utf-8")


def decode_request(payload: dict[str, Any]) -> NDArray[np.float32]:
    """Inverse of ``encode_request`` for the remote function."""
    return _decode_array(payload, "shape", "data_b64", "image")


def response_body(
    masks: NDArray[np.float32],
    scores: NDArray[np.float32],
    inference_seconds: float,
) -> dict[str, Any]:
    """JSON object the endpoint returns, including its own elapsed time."""
    masks_array = np.ascontiguousarray(masks, dtype=np.float32)
    scores_array = np.ascontiguousarray(scores, dtype=np.float32)
    return {
        "masks_shape": [int(dim) for dim in masks_array.shape],
        "masks_b64": base64.b64encode(masks_array.tobytes()).decode("ascii"),
        "scores_shape": [int(dim) for dim in scores_array.shape],
        "scores_b64": base64.b64encode(scores_array.tobytes()).decode("ascii"),
        "inference_seconds": float(inference_seconds),
    }


def decode_response(raw: bytes) -> tuple[NDArray[np.float32], NDArray[np.float32], float]:
    """Parse masks, scores, and remote inference seconds."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Sam3Unavailable("Modal SAM response was not JSON") from exc
    if not isinstance(payload, dict):
        raise Sam3Unavailable("Modal SAM response was not a JSON object")
    body = cast(dict[str, Any], payload)
    masks = _decode_array(body, "masks_shape", "masks_b64", "masks")
    scores = _decode_array(body, "scores_shape", "scores_b64", "scores")
    if masks.ndim != 4 or masks.shape[0] != 1:
        raise Sam3Unavailable("Modal SAM masks must have shape [1, N, H, W]")
    if scores.ndim != 2 or scores.shape[0] != 1:
        raise Sam3Unavailable("Modal SAM scores must have shape [1, N]")
    if masks.shape[1] != scores.shape[1]:
        raise Sam3Unavailable("Modal SAM masks and scores disagree on how many objects")
    seconds = body.get("inference_seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, int | float):
        raise Sam3Unavailable("Modal SAM response is missing inference_seconds")
    elapsed = float(seconds)
    if elapsed < 0 or not math.isfinite(elapsed):
        raise Sam3Unavailable("Modal SAM inference_seconds is not a usable duration")
    return masks, scores, elapsed


def post_json(url: str, body: bytes, *, timeout_s: float) -> bytes:
    """POST JSON with the stdlib client. No Modal SDK."""
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return cast(bytes, response.read())
    except urllib.error.HTTPError as exc:
        raise Sam3Unavailable(f"Modal SAM endpoint returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise Sam3Unavailable(f"Modal SAM endpoint request failed: {exc.reason}") from exc


class ModalSamSession:
    """``Sam3Session`` that calls the deployed Modal web endpoint."""

    def __init__(
        self,
        url: str | None = None,
        *,
        input_size: tuple[int, int] | None = None,
        model: str | None = None,
        on_usage: UsageHook | None = None,
        on_gpu_seconds: GpuSecondsHook | None = None,
        before_call: BeforeCall | None = None,
        poster: Poster | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        self._url = resolve_modal_url(url)
        self._input_size = resolve_input_size(input_size)
        self._model = usage_model_name(model)
        self._on_usage = on_usage
        self._on_gpu_seconds = on_gpu_seconds
        self._before_call = before_call
        self._poster = poster if poster is not None else _poster(timeout_s)

    @property
    def provider(self) -> str:
        return "modal"

    @property
    def input_size(self) -> tuple[int, int]:
        return self._input_size

    def run(
        self, image_chw: NDArray[np.float32]
    ) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        """POST one tensor. ``before_call('modal')`` may raise to block it."""
        if self._before_call is not None:
            self._before_call("modal")
        raw = self._poster(self._url, encode_request(image_chw))
        masks, scores, elapsed = decode_response(raw)
        if self._on_usage is not None:
            self._on_usage("modal", self._model, 0, 0, None)
        if self._on_gpu_seconds is not None:
            self._on_gpu_seconds(elapsed)
        return masks, scores


def modal_sam_detector(
    *,
    label: str = "object",
    url: str | None = None,
    input_size: tuple[int, int] | None = None,
    model: str | None = None,
    on_usage: UsageHook | None = None,
    on_gpu_seconds: GpuSecondsHook | None = None,
    before_call: BeforeCall | None = None,
    poster: Poster | None = None,
) -> Sam3Detector:
    """A ``Sam3Detector`` whose session is the Modal endpoint."""
    session = ModalSamSession(
        url,
        input_size=input_size,
        model=model,
        on_usage=on_usage,
        on_gpu_seconds=on_gpu_seconds,
        before_call=before_call,
        poster=poster,
    )
    return Sam3Detector(session, label=label)


def _poster(timeout_s: float) -> Poster:
    def send(url: str, body: bytes) -> bytes:
        return post_json(url, body, timeout_s=timeout_s)

    return send


def _shape(value: Any, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise Sam3Unavailable(f"Modal SAM {label} shape is missing")
    dims: list[int] = []
    for dim in value:
        if isinstance(dim, bool) or not isinstance(dim, int) or dim < 1:
            raise Sam3Unavailable(f"Modal SAM {label} shape is missing")
        dims.append(dim)
    return tuple(dims)


def _decode_array(
    payload: dict[str, Any], shape_key: str, data_key: str, label: str
) -> NDArray[np.float32]:
    shape = _shape(payload.get(shape_key), label)
    data_raw = payload.get(data_key)
    if not isinstance(data_raw, str):
        raise Sam3Unavailable(f"Modal SAM {label} data is missing")
    try:
        raw = base64.b64decode(data_raw, validate=True)
    except ValueError as exc:
        raise Sam3Unavailable(f"Modal SAM {label} data is not base64") from exc
    count = 1
    for dim in shape:
        count *= dim
    if len(raw) != count * 4:
        raise Sam3Unavailable(f"Modal SAM {label} data does not match its shape")
    flat = np.frombuffer(raw, dtype=np.float32)
    return np.array(flat, dtype=np.float32, copy=True).reshape(shape)
