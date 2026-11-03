"""Modal app: the simulated drone — the CM5 survey server on one CPU container.

Module-level ``app``, ``image`` and ``serve``. Do not import this module from tests; CI does not
install ``modal``. What it runs is ``surmap.survey.modal_hosting.cm5_command``, tested there.

The image builds RTAB-Map and ``surmap-rtabmap-stream`` natively with
``scripts/build_rtabmap_native.sh`` (Modal runs no Docker inside a container). The server takes
each stream's camera definitions from its config, so no calibration is baked in. One container
(``max_containers=1``): a survey's region queries must reach the server that holds its frames.

Deploy from the repo root and stop (full steps in ``docs/modal.md``):

    uv run --with modal modal deploy src/surmap/survey/modal_cm5_app.py
    uv run --with modal modal app stop surmap-cm5-sim
"""

from __future__ import annotations

import os
import subprocess

import modal

from surmap.survey.modal_hosting import (
    CM5_APP_NAME,
    CM5_PORT,
    RTABMAP_WORK,
    SURVEY_SECRET,
    cm5_command,
)

_TIMEOUT_S = int(os.environ.get("SURMAP_MODAL_TIMEOUT", "86400"))
_SCALEDOWN_S = int(os.environ.get("SURMAP_MODAL_SCALEDOWN_WINDOW", "300"))

app = modal.App(CM5_APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .add_local_file(
        "scripts/build_rtabmap_native.sh", "/opt/surmap/scripts/build_rtabmap_native.sh", copy=True
    )
    .add_local_dir("deploy/rtabmap-stream", "/opt/surmap/deploy/rtabmap-stream", copy=True)
    .run_commands(f"RTABMAP_WORK={RTABMAP_WORK} bash /opt/surmap/scripts/build_rtabmap_native.sh")
    .pip_install_from_pyproject("pyproject.toml")
    .add_local_python_source("surmap")
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name(SURVEY_SECRET)],
    timeout=_TIMEOUT_S,
    scaledown_window=_SCALEDOWN_S,
    max_containers=1,
)
@modal.concurrent(max_inputs=100)
@modal.web_server(CM5_PORT, startup_timeout=120)
def serve() -> None:
    """Start the CM5 server; Modal routes the app's HTTPS URL (and its WebSockets) to it."""
    subprocess.Popen(cm5_command())
