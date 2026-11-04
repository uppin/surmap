"""Modal app: the base station — SAM 3.1 (PyTorch) behind ``StationSamService`` on one GPU.

Module-level ``app``, ``image`` and ``serve``. Do not import this module from tests; CI does not
install ``modal``. What it runs and how it is configured live in ``surmap.survey.modal_hosting``
(``station_command``, ``StationSettings``), tested there.

The SAM 3.1 checkpoint (``facebook/sam3.1``, gated) is downloaded on first start into Volume
``surmap-sam3`` with the ``huggingface`` secret's ``HF_TOKEN``, the same volume and secret the
``surmap-sam`` app uses. The GPU is an L4 (24 GB), or an A10G when no L4 is free;
``SURMAP_MODAL_GPU`` names another order (``A10G`` or ``L4,A100``). ``SURMAP_STATION_LABEL`` is
the SAM concept prompt when a client sends none.

Deploy from the repo root and stop (full steps in ``docs/modal.md``):

    uv run --with modal modal deploy src/surmap/survey/modal_station_app.py
    uv run --with modal modal app stop surmap-station
"""

from __future__ import annotations

import os
import subprocess
import sys

import modal

from surmap.survey.modal_hosting import (
    MODEL_MOUNT,
    SAM3_PACKAGE,
    SAM3_RUNTIME_PACKAGES,
    STATION_APP_NAME,
    STATION_PORT,
    SURVEY_SECRET,
    StationSettings,
    station_command,
)

VOLUME_NAME = "surmap-sam3"
HF_SECRET = "huggingface"

# Read where the app is deployed, and again in the container from the secret built below.
_SETTINGS = StationSettings.from_env(os.environ)

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
    # The same SAM 3.1 runtime as modal_sam_app.py: what sam3 declares (minus its numpy<2 pin)
    # and the imports it does not declare.
    .pip_install(
        *SAM3_RUNTIME_PACKAGES,
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
    )
    # surmap's dependencies into the same interpreter as torch and sam3 (a uv_sync venv would
    # not see them); numpy is surmap's pin.
    .pip_install_from_pyproject("pyproject.toml")
    # sam3 itself, without resolving its numpy<2 pin against surmap's.
    .pip_install(SAM3_PACKAGE, extra_options="--no-deps")
    .add_local_python_source("surmap", ignore=["**/__pycache__"])
)

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


@app.function(
    image=image,
    gpu=_SETTINGS.gpus,
    secrets=[
        modal.Secret.from_name(SURVEY_SECRET),
        modal.Secret.from_name(HF_SECRET),
        modal.Secret.from_dict(_SETTINGS.container_env()),
    ],
    volumes={MODEL_MOUNT: volume},
    cpu=4.0,
    memory=16384,
    timeout=_SETTINGS.timeout_s,
    scaledown_window=_SETTINGS.scaledown_s,
    max_containers=1,
)
@modal.concurrent(max_inputs=100)
@modal.web_server(STATION_PORT, startup_timeout=600)
def serve() -> None:
    """Start the station server; Modal routes the app's HTTPS URL (and its WebSockets) to it."""
    # This function's interpreter, with surmap on its path.
    subprocess.Popen([sys.executable, *station_command(_SETTINGS.label)[1:]])
