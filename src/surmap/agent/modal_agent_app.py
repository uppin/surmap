"""Modal app: the survey agent and its chat page, behind a pass code, on one CPU container.

Module-level ``app``, ``image`` and ``serve``. Do not import this module from tests; CI does not
install ``modal``. What it runs is ``surmap.survey.modal_hosting.agent_command``, tested there.

One container (``max_containers=1``): the agent's SQLite DBs and files — demo history,
conversations, the simulation store and the usage log — live under ``/cache`` on Volume
``surmap-agent-cache`` (see ``agent_command``), so they survive a container restart on
Modal's background commits; running turns and jobs do not. Its SAM runs on
the deployed ``surmap-station`` app (``--station modal``; inside Modal the SDK needs no token).
Secrets: ``surmap-agent`` (``MODEL_API_KEY``, ``SURMAP_AGENT_ACCESS_CODE``) and
``surmap-survey`` (the station's bearer token). The demo cache is Volume ``surmap-agent-cache``.

The image also carries the Bevy simulation the agent serves at ``/sim/``: the PoC's
``trunk build`` and its assets with the fetched pinned files. Deploying refuses a page older
than its sources, unfetched assets, or either page without its third-party licence file
(``check_sim_bundle``, ``check_chat_bundle``); only the deploy checks, since the container
imports this file without the PoC on disk.

Build the pages and fetch the assets first, then deploy from the repo root (full steps in
``docs/modal.md``):

    (cd web/agent-chat && yarn build)
    uv run python scripts/fetch_sim_assets.py
    (cd examples/bevy-sitl-poc && trunk build index.html --release)
    uv run python scripts/sim_notices.py
    uv run --with modal modal deploy src/surmap/agent/modal_agent_app.py
    uv run --with modal modal app stop surmap-agent
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import modal

from surmap.survey.modal_hosting import (
    AGENT_APP_NAME,
    AGENT_CACHE,
    AGENT_PORT,
    AGENT_SECRET,
    AGENT_SIM_ASSETS,
    AGENT_SIM_PAGE,
    AGENT_WEB_DIST,
    SURVEY_SECRET,
    agent_command,
    check_chat_bundle,
    check_sim_bundle,
)

CACHE_VOLUME = "surmap-agent-cache"

_TIMEOUT_S = int(os.environ.get("SURMAP_MODAL_TIMEOUT", "86400"))
_SCALEDOWN_S = int(os.environ.get("SURMAP_MODAL_SCALEDOWN_WINDOW", "1200"))

if modal.is_local():
    check_chat_bundle(Path("web/agent-chat/dist"))
    check_sim_bundle(Path("examples/bevy-sitl-poc"))

app = modal.App(AGENT_APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.11")
    # The locked dependencies (uv.lock) with the Modal SDK for the station control, then the
    # built chat page, the simulation (its page and assets) and surmap itself.
    .uv_sync(extra_options="--no-dev --extra modal")
    .add_local_dir("web/agent-chat/dist", AGENT_WEB_DIST)
    .add_local_dir("examples/bevy-sitl-poc/assets", AGENT_SIM_ASSETS)
    # Not a local `dist/assets` link to the assets (PoC README): /sim/assets/ is served from those.
    .add_local_dir("examples/bevy-sitl-poc/dist", AGENT_SIM_PAGE, ignore=["assets"])
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
