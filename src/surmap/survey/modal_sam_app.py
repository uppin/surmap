"""Modal app that runs the SAM 3.1 ONNX export on one GPU.

Deploy and stop from the repo root. The token from ``modal token new``
stays in ``~/.modal.toml``. Licence, the checkpoint, spend, and
``MODAL_SAM_INPUT`` are in ``docs/modal-sam.md``.

    uv run --with modal modal deploy src/surmap/survey/modal_sam_app.py
    uv run --with modal modal app stop surmap-sam

Default GPU is ``T4`` (``SURMAP_MODAL_GPU``), ``timeout`` is 300
seconds, ``scaledown_window`` is 60 seconds, and ``max_containers`` is
1. There is no ``min_containers``. Importing this module does not
require Modal. ``app`` is ``None`` until the package imports.
"""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from surmap.survey.modal_sam import (
    APP_NAME,
    MODEL_DIR,
    MODEL_FILENAME,
    REMOTE_PIP_PACKAGES,
    VOLUME_NAME,
    decode_request,
    modal_function_kwargs,
    response_body,
)
from surmap.survey.sam3 import OnnxSam3Session, Sam3Session

_SESSION: OnnxSam3Session | None = None


def gpu_session() -> OnnxSam3Session:
    """Load the Volume checkpoint once per container, on the CUDA provider."""
    global _SESSION
    if _SESSION is None:
        _SESSION = OnnxSam3Session(Path(MODEL_DIR) / MODEL_FILENAME, device="cuda")
    return _SESSION


def segment_payload(
    payload: dict[str, Any],
    *,
    session: Sam3Session,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    """Run one tensor and return masks, scores, and this call's elapsed time."""
    image = decode_request(payload)
    started = clock()
    masks, scores = session.run(image)
    return response_body(masks, scores, clock() - started)


def build_app(modal: Any, *, environ: Mapping[str, str] | None = None) -> Any:
    """Register the web endpoint. ``modal`` is the SDK module or a test double."""
    limits = modal_function_kwargs(environ)
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install(*REMOTE_PIP_PACKAGES)
        .add_local_python_source("surmap")
    )
    volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
    built = modal.App(APP_NAME)

    def segment(item: dict[str, Any]) -> dict[str, Any]:
        return segment_payload(item, session=gpu_session())

    # Applied as calls so mypy does not treat the Modal SDK as an untyped
    # decorator. Order matches ``@app.function`` above ``@fastapi_endpoint``.
    endpoint = modal.fastapi_endpoint(method="POST")
    register = built.function(image=image, volumes={MODEL_DIR: volume}, **limits)
    built.segment = register(endpoint(segment))
    return built


def load_app(
    loader: Callable[[str], Any] = importlib.import_module,
    *,
    environ: Mapping[str, str] | None = None,
) -> Any | None:
    """Build the App when Modal is installed. Otherwise return ``None``."""
    try:
        modal = loader("modal")
    except ImportError:
        return None
    return build_app(modal, environ=environ)


app = load_app()
