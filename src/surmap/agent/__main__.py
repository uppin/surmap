"""The survey agent's chat server: `python -m surmap.agent`.

    uv run python -m surmap.agent --sam-fake --model ollama:llama3.2

Serves `ChatService`, `AgentJobs` and `SurveyTools` over Connect plus the geometry, frame and
health routes on hypercorn, on 127.0.0.1:8780 unless `--host` / `--port` say otherwise. Browser
origins allowed by CORS come from `SURMAP_AGENT_CORS_ORIGINS` (comma-separated; default the
chat UI's Vite dev server, `http://localhost:5173`).
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path

from surmap.agent.server.app import DEFAULT_HOST, DEFAULT_MODEL_ID, DEFAULT_PORT, AgentServerConfig

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
    raise NotImplementedError  # TODO(pr-8): implement


async def serve(config: AgentServerConfig) -> None:
    """Serve the agent on `config.host:config.port` until cancelled; always stop the host."""
    raise NotImplementedError  # TODO(pr-8): implement


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line and serve until signalled."""
    raise NotImplementedError  # TODO(pr-8): implement


if __name__ == "__main__":
    main()
