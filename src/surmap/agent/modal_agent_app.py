"""Modal app: the survey agent and its chat page, behind a pass code, on one CPU container.

Module-level ``app``, ``image`` and ``serve``. Do not import this module from tests; CI does not
install ``modal``. What it runs is ``surmap.survey.modal_hosting.agent_command``, tested there.

One container (``max_containers=1``): conversations live in the agent's memory. Its SAM runs on
the deployed ``surmap-station`` app (``--station modal``; inside Modal the SDK needs no token).
Secrets: ``surmap-agent`` (``MODEL_API_KEY``, ``SURMAP_AGENT_ACCESS_CODE``) and
``surmap-survey`` (the station's bearer token). The demo cache is Volume ``surmap-agent-cache``.

Build the page first, then deploy from the repo root (full steps in ``docs/modal.md``):

    (cd web/agent-chat && yarn build)
    uv run --with modal modal deploy src/surmap/agent/modal_agent_app.py
    uv run --with modal modal app stop surmap-agent
"""

from __future__ import annotations

import os
import subprocess
import sys

import modal

from surmap.survey.modal_hosting import (
    AGENT_APP_NAME,
    AGENT_CACHE,
    AGENT_PORT,
    AGENT_SECRET,
    AGENT_WEB_DIST,
    SURVEY_SECRET,
    agent_command,
)

CACHE_VOLUME = "surmap-agent-cache"

_TIMEOUT_S = int(os.environ.get("SURMAP_MODAL_TIMEOUT", "86400"))
_SCALEDOWN_S = int(os.environ.get("SURMAP_MODAL_SCALEDOWN_WINDOW", "1200"))

app = modal.App(AGENT_APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.11")
    # The locked dependencies (uv.lock) with the Modal SDK for the station control, then the
    # built chat page and surmap itself.
    .uv_sync(extra_options="--no-dev --extra modal")
    .add_local_dir("web/agent-chat/dist", AGENT_WEB_DIST)
    .add_local_python_source("surmap", ignore=["**/__pycache__"])
)

volume = modal.Volume.from_name(CACHE_VOLUME, create_if_missing=True)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name(AGENT_SECRET), modal.Secret.from_name(SURVEY_SECRET)],
    volumes={AGENT_CACHE: volume},
    cpu=2.0,
    memory=4096,
    timeout=_TIMEOUT_S,
    scaledown_window=_SCALEDOWN_S,
    max_containers=1,
)
@modal.concurrent(max_inputs=100)
@modal.web_server(AGENT_PORT, startup_timeout=120)
def serve() -> None:
    """Start the agent; Modal routes the app's HTTPS URL to it."""
    # This function's interpreter: the image's uv environment, with surmap on its path.
    subprocess.Popen([sys.executable, *agent_command()[1:]])
