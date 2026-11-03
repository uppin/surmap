"""The survey agent's chat server: `python -m surmap.agent`.

    uv run python -m surmap.agent --sam-fake --model ollama:llama3.2

Serves `ChatService`, `AgentJobs` and `SurveyTools` over Connect plus the geometry, frame and
health routes on hypercorn, on 127.0.0.1:8780 unless `--host` / `--port` say otherwise. Browser
origins allowed by CORS come from `SURMAP_AGENT_CORS_ORIGINS` (comma-separated; default the
chat UI's Vite dev server, `http://localhost:5173`).
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from surmap.agent.server.app import (
    CORS_ORIGINS_ENV,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_HOST,
    DEFAULT_MODEL_ID,
    DEFAULT_PORT,
    AgentServerConfig,
    build_agent_description,
    build_demo_workspace,
)
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
    return AgentServerConfig(
        host=args.host,
        port=args.port,
        history_db=args.history_db,
        cache_dir=args.cache_dir,
        model_id=args.model,
        sam_fake=args.sam_fake,
        cors_origins=cors_origins,
    )


async def serve(config: AgentServerConfig) -> None:
    """Serve the agent on `config.host:config.port` until cancelled; always stop the host."""
    workspace = build_demo_workspace(config)
    description = build_agent_description(config, workspace=workspace, geometry=workspace.geometry)
    host = HypercornHost(description, None, host=config.host, port=config.port)
    ports = await host.start()
    print(f"survey agent on http://{config.host}:{ports.public}", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await host.stop()


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line and serve until signalled; Ctrl-C stops it cleanly — `serve`
    has already stopped the host when `asyncio.run` re-raises the interrupt."""
    config = config_from_args(argv)
    try:
        asyncio.run(serve(config))
    except KeyboardInterrupt:
        print("survey agent stopped", flush=True)


if __name__ == "__main__":
    main()
