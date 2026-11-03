"""Modal app: the base station — SAM 3.1 (PyTorch) behind ``StationSamService`` on one GPU.

Module-level ``app``, ``image`` and ``serve``. Do not import this module from tests; CI does not
install ``modal``. What it runs is ``surmap.survey.modal_hosting.station_command``, tested there.

The SAM 3.1 checkpoint (``facebook/sam3.1``, gated) is downloaded on first start into Volume
``surmap-sam3`` with the ``huggingface`` secret's ``HF_TOKEN``, the same volume and secret the
``surmap-sam`` app uses. The default GPU is an L4 (24 GB); ``SURMAP_MODAL_GPU`` overrides it.

Deploy from the repo root and stop (full steps in ``docs/modal.md``):

    uv run --with modal modal deploy src/surmap/survey/modal_station_app.py
    uv run --with modal modal app stop surmap-station
"""

from __future__ import annotations

import os
import subprocess

import modal

from surmap.survey.modal_hosting import (
    MODEL_MOUNT,
    STATION_APP_NAME,
    STATION_PORT,
    SURVEY_SECRET,
    station_command,
)

VOLUME_NAME = "surmap-sam3"
HF_SECRET = "huggingface"

_GPU = os.environ.get("SURMAP_MODAL_GPU", "L4")
_TIMEOUT_S = int(os.environ.get("SURMAP_MODAL_TIMEOUT", "86400"))
_SCALEDOWN_S = int(os.environ.get("SURMAP_MODAL_SCALEDOWN_WINDOW", "300"))
_LABEL = os.environ.get("SURMAP_STATION_LABEL", "object")

app = modal.App(STATION_APP_NAME)

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
    # The same SAM 3.1 runtime as modal_sam_app.py, including the imports sam3 does not declare.
    .pip_install(
        "sam3 @ git+https://github.com/facebookresearch/sam3.git",
        "setuptools<81",  # sam3 imports pkg_resources, removed in setuptools 81
        "einops",
        "decord",
        "pycocotools",
        "opencv-python-headless",
        "scipy",
        "scikit-image",
        "psutil",
        "matplotlib",
        "omegaconf",
        "hydra-core",
        "iopath>=0.1.10",
        "ftfy==6.1.1",
        "regex",
        "timm>=1.0.17",
    )
    .pip_install_from_pyproject("pyproject.toml")
    .add_local_python_source("surmap")
)

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


@app.function(
    image=image,
    gpu=_GPU,
    secrets=[modal.Secret.from_name(SURVEY_SECRET), modal.Secret.from_name(HF_SECRET)],
    volumes={MODEL_MOUNT: volume},
    timeout=_TIMEOUT_S,
    scaledown_window=_SCALEDOWN_S,
    max_containers=1,
)
@modal.concurrent(max_inputs=100)
@modal.web_server(STATION_PORT, startup_timeout=600)
def serve() -> None:
    """Start the station server; Modal routes the app's HTTPS URL (and its WebSockets) to it."""
    subprocess.Popen(station_command(_LABEL))
