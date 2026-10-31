"""Modal app: SAM 3.1 PyTorch checkpoint on one GPU.

Module-level ``app``, ``image``, and ``segment``. Modal 1.x rejects a
function defined inside another function. Do not import this module
from tests; CI does not install ``modal``. Behaviour of the JSON
contract is tested in ``surmap.survey.modal_sam``.

Deploy and stop (full steps in ``docs/modal.md``):

    uv run --with modal modal deploy src/surmap/survey/modal_sam_app.py
    uv run --with modal modal app stop surmap-sam

The default GPU is an L4 (24 GB). A T4's 16 GB is tight for the 3.5 GB
``sam3.1_multiplex.pt`` checkpoint plus the image backbone's
activations. ``SURMAP_MODAL_GPU`` overrides it (for example ``A10G``,
also 24 GB). ``timeout`` is 300 seconds, ``scaledown_window`` is 60
seconds, ``max_containers`` is 1, and ``min_containers`` is unset.
"""

from __future__ import annotations

import os
from typing import Any

import modal

from surmap.survey.modal_sam import pack_detections

APP_NAME = "surmap-sam"
DEFAULT_GPU = "L4"
VOLUME_NAME = "surmap-sam3"
MODEL_MOUNT = "/models"
HF_SECRET = "huggingface"

_GPU = os.environ.get("SURMAP_MODAL_GPU", DEFAULT_GPU)
_TIMEOUT_S = int(os.environ.get("SURMAP_MODAL_TIMEOUT", "900"))
_SCALEDOWN_S = int(os.environ.get("SURMAP_MODAL_SCALEDOWN_WINDOW", "60"))

app = modal.App(APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .env(
        {
            "HF_HOME": f"{MODEL_MOUNT}/hf",
            "HUGGINGFACE_HUB_CACHE": f"{MODEL_MOUNT}/hf/hub",
        }
    )
    .pip_install(
        "torch",
        "torchvision",
        extra_index_url="https://download.pytorch.org/whl/cu124",
    )
    .pip_install(
        "sam3 @ git+https://github.com/facebookresearch/sam3.git",
        "fastapi[standard]",
        "pillow",
    )
    .add_local_python_source("surmap")
)

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
secret = modal.Secret.from_name(HF_SECRET)

_MODEL: Any = None
_PROCESSOR: Any = None


def _numpy(value: Any) -> Any:
    import numpy as np

    if hasattr(value, "detach"):
        value = value.detach().float().cpu().numpy()
    return np.asarray(value)


def _load_sam() -> tuple[Any, Any]:
    """Download ``facebook/sam3.1`` into the volume, then build the image model."""
    global _MODEL, _PROCESSOR
    if _PROCESSOR is not None and _MODEL is not None:
        return _MODEL, _PROCESSOR
    os.environ.setdefault("HF_HOME", f"{MODEL_MOUNT}/hf")
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", f"{MODEL_MOUNT}/hf/hub")
    from sam3.model.sam3_image_processor import Sam3Processor
    from sam3.model_builder import build_sam3_image_model, download_ckpt_from_hf

    checkpoint = download_ckpt_from_hf(version="sam3.1")
    volume.commit()  # keep the checkpoint even if model build fails later
    _MODEL = build_sam3_image_model(
        checkpoint_path=checkpoint,
        load_from_HF=False,
        device="cuda",
    )
    _PROCESSOR = Sam3Processor(_MODEL, device="cuda", confidence_threshold=0.5)
    volume.commit()
    return _MODEL, _PROCESSOR


def _open_image(item: dict[str, Any]) -> Any:
    import base64
    import io

    from PIL import Image

    encoded = item.get("image_b64")
    if not isinstance(encoded, str) or not encoded.strip():
        raise ValueError("image_b64 is required")
    raw = base64.b64decode(encoded)
    image = Image.open(io.BytesIO(raw))
    return image.convert("RGB")


@app.function(
    image=image,
    gpu=_GPU,
    timeout=_TIMEOUT_S,
    scaledown_window=_SCALEDOWN_S,
    max_containers=1,
    volumes={MODEL_MOUNT: volume},
    secrets=[secret],
)
@modal.fastapi_endpoint(method="POST")
def segment(item: dict[str, Any]) -> dict[str, Any]:
    """Text-prompt SAM 3.1. Returns boxes, polygons, scores, and GPU seconds."""
    import time

    prompt = item.get("prompt")
    text = prompt.strip() if isinstance(prompt, str) and prompt.strip() else "person"
    image = _open_image(item)
    _model, processor = _load_sam()
    del _model
    started = time.perf_counter()
    state = processor.set_image(image)
    output = processor.set_text_prompt(state=state, prompt=text)
    elapsed = time.perf_counter() - started
    width, height = image.size
    return pack_detections(
        text,
        _numpy(output["masks"]),
        _numpy(output["boxes"]),
        _numpy(output["scores"]),
        image_width=width,
        image_height=height,
        inference_seconds=elapsed,
    )
