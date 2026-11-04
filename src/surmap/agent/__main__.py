"""The survey agent's chat server: `python -m surmap.agent`.

    uv run python -m surmap.agent --sam-fake --model ollama:llama3.2

Serves `ChatService`, `AgentJobs` and `SurveyTools` over Connect plus the geometry, frame and
health routes on hypercorn, on 127.0.0.1:8780 unless `--host` / `--port` say otherwise. Browser
origins allowed by CORS come from `SURMAP_AGENT_CORS_ORIGINS` (comma-separated; default the
chat UI's Vite dev server, `http://localhost:5173`). Provider keys (`MODEL_API_KEY`,
`FIREWORKS_API_KEY`) may live in the project `.env`; `main` loads it first and a shell export wins.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from surmap.agent.server.app import (
    CORAL_MODEL_DIR_ENV,
    CORS_ORIGINS_ENV,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_HOST,
    DEFAULT_MODEL_ID,
    DEFAULT_PORT,
    DEFAULT_SIM_ASSETS,
    SKETCHFAB_TOKEN_ENV,
    SKILLS_DIR_ENV,
    AgentServerConfig,
    build_agent_description,
    build_demo_workspace,
    build_simulation_rig,
)
from surmap.agent.tools.onboard import ONBOARD_OFF
from surmap.detection import DEFAULT_PROFILE, MODEL_PROFILES
from surmap.env import load_env
from surmap.rpc.hosts.hypercorn import HypercornHost

__all__ = ["build_parser", "config_from_args", "main", "serve"]


def build_parser() -> argparse.ArgumentParser:
    """The agent process command line."""
    parser = argparse.ArgumentParser(prog="python -m surmap.agent")
    parser.add_argument("--host", default=DEFAULT_HOST, help="bind address (default loopback)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--history-db", type=Path, default=None, help="demo run history DB")
    parser.add_argument("--cache-dir", type=Path, default=None, help="demo scene cache")
    parser.add_argument(
        "--model", default=DEFAULT_MODEL_ID, help="default model id, e.g. ollama:llama3.2"
    )
    parser.add_argument("--sam-fake", action="store_true", help="fake centred-box SAM")
    parser.add_argument(
        "--coral-model-dir",
        type=Path,
        default=None,
        help="prepared Coral model dir for on-board detection "
        f"(default: ${CORAL_MODEL_DIR_ENV}; none: no on-board model)",
    )
    parser.add_argument(
        "--coral-model",
        choices=[*sorted(MODEL_PROFILES), ONBOARD_OFF],
        default=DEFAULT_PROFILE,
        help="on-board model a run uses when the agent names none; none for no on-board model",
    )
    parser.add_argument(
        "--sim-dir",
        type=Path,
        default=None,
        help="simulation store: simulation.sqlite + library/ (default <cache>/simulation)",
    )
    parser.add_argument(
        "--sim-assets",
        type=Path,
        default=DEFAULT_SIM_ASSETS,
        help="the Bevy simulation's assets/ (scene, camera profiles, pinned textures)",
    )
    parser.add_argument(
        "--sim-dist", type=Path, default=None, help="a `trunk build` output served at /sim/"
    )
    return parser


def config_from_args(
    argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None
) -> AgentServerConfig:
    """The config for this command line; CORS origins from `SURMAP_AGENT_CORS_ORIGINS` in
    `environ` (default `os.environ`), blank entries dropped."""
    args = build_parser().parse_args(argv)
    env = os.environ if environ is None else environ
    raw_origins = env.get(CORS_ORIGINS_ENV)
    cors_origins = (
        DEFAULT_CORS_ORIGINS
        if raw_origins is None
        else tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())
    )
    raw_skills_dir = env.get(SKILLS_DIR_ENV)
    raw_coral_dir = env.get(CORAL_MODEL_DIR_ENV)
    coral_model_dir = args.coral_model_dir or (Path(raw_coral_dir) if raw_coral_dir else None)
    return AgentServerConfig(
        host=args.host,
        port=args.port,
        history_db=args.history_db,
        cache_dir=args.cache_dir,
        model_id=args.model,
        sam_fake=args.sam_fake,
        cors_origins=cors_origins,
        skills_dir=Path(raw_skills_dir) if raw_skills_dir else None,
        sim_dir=args.sim_dir,
        sim_assets=args.sim_assets,
        sim_dist=args.sim_dist,
        sketchfab_token=env.get(SKETCHFAB_TOKEN_ENV) or None,
        coral_model_dir=coral_model_dir,
        coral_model=args.coral_model,
    )


async def serve(config: AgentServerConfig) -> None:
    """Serve the agent on `config.host:config.port` until cancelled; always stop the host."""
    workspace = build_demo_workspace(config)
    description = build_agent_description(
        config,
        workspace=workspace,
        geometry=workspace.geometry,
        simulation=build_simulation_rig(config),
    )
    host = HypercornHost(description, None, host=config.host, port=config.port)
    ports = await host.start()
    print(f"survey agent on http://{config.host}:{ports.public}", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await host.stop()


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line and serve until signalled; Ctrl-C stops it cleanly — `serve`
    has already stopped the host when `asyncio.run` re-raises the interrupt. The project `.env`
    fills environment gaps first (keys only; a shell export wins)."""
    load_env()
    config = config_from_args(argv)
    try:
        asyncio.run(serve(config))
    except KeyboardInterrupt:
        print("survey agent stopped", flush=True)


if __name__ == "__main__":
    main()
