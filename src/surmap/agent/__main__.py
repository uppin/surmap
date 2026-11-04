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
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from surmap.agent.runtime.outputs import DEFAULT_MAX_INLINE_BYTES
from surmap.agent.server.app import (
    CORAL_MODEL_DIR_ENV,
    CORS_ORIGINS_ENV,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_HOST,
    DEFAULT_MODEL_ID,
    DEFAULT_PORT,
    DEFAULT_SIM_ASSETS,
    MAX_INLINE_OUTPUT_ENV,
    READ_ROOTS_ENV,
    SKETCHFAB_TOKEN_ENV,
    SKILLS_DIR_ENV,
    AgentServerConfig,
    build_agent_description,
    build_demo_workspace,
    build_simulation_rig,
    build_station,
    default_state_dir,
    start_bevy_bridge,
)
from surmap.agent.tools.onboard import ONBOARD_OFF
from surmap.agent.tools.station import DEFAULT_IDLE_TIMEOUT_S, IdleTicker
from surmap.detection import DEFAULT_PROFILE, MODEL_PROFILES
from surmap.env import load_env
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.survey.endpoint import survey_token
from surmap.survey.modal_hosting import STATION_APP_NAME

__all__ = ["build_parser", "config_from_args", "main", "serve"]

ACCESS_CODE_ENV = "SURMAP_AGENT_ACCESS_CODE"
"""The pass code the agent gates every call behind; unset: no gate."""


def build_parser() -> argparse.ArgumentParser:
    """The agent process command line."""
    parser = argparse.ArgumentParser(prog="python -m surmap.agent")
    parser.add_argument("--host", default=DEFAULT_HOST, help="bind address (default loopback)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="where conversations, map scenes, runs, scenarios and tool outputs persist "
        "(default: --cache-dir, else $SURMAP_DEMO_CACHE_DIR or ~/.cache/surmap)",
    )
    parser.add_argument(
        "--history-db", type=Path, default=None, help="demo run history DB (default <state>)"
    )
    parser.add_argument(
        "--conversations-db",
        type=Path,
        default=None,
        help="chat conversations DB (history, model, replay); default <state>/conversations.sqlite",
    )
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
    parser.add_argument(
        "--bevy-bridge-port",
        type=int,
        default=None,
        help="serve the stereo bridge a ?bridge= simulation page streams its active drone to",
    )
    parser.add_argument(
        "--station",
        choices=("modal", "stub"),
        default=None,
        help="run SAM on a station: the deployed Modal app (needs `uv sync --extra modal` and a "
        "Modal token) or an in-process stub; up on first use, down when idle",
    )
    parser.add_argument(
        "--station-app", default=STATION_APP_NAME, help="the station's deployed Modal app"
    )
    parser.add_argument(
        "--station-env", default=None, help="its Modal environment (default: the profile's)"
    )
    parser.add_argument(
        "--station-idle-s",
        type=int,
        default=DEFAULT_IDLE_TIMEOUT_S,
        help="stop the station after this many seconds without a SAM frame",
    )
    parser.add_argument(
        "--station-prompt", default="object", help="SAM concept a station link starts with"
    )
    parser.add_argument(
        "--web-dist", type=Path, default=None, help="a built chat page (yarn build) served at /"
    )
    return parser


def config_from_args(
    argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None
) -> AgentServerConfig:
    """The config for this command line; CORS origins from `SURMAP_AGENT_CORS_ORIGINS` in
    `environ` (default `os.environ`), blank entries dropped, and likewise the read roots from
    `SURMAP_AGENT_READ_ROOTS` (`os.pathsep`-separated).

    Raises `ValueError` when `SURMAP_AGENT_MAX_INLINE_OUTPUT_BYTES` is not a positive integer.
    """
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
        state_dir=args.state_dir or args.cache_dir or default_state_dir(env),
        history_db=args.history_db,
        conversations_db=args.conversations_db,
        cache_dir=args.cache_dir,
        model_id=args.model,
        sam_fake=args.sam_fake,
        cors_origins=cors_origins,
        skills_dir=Path(raw_skills_dir) if raw_skills_dir else None,
        sim_dir=args.sim_dir,
        sim_assets=args.sim_assets,
        sim_dist=args.sim_dist,
        bevy_bridge_port=args.bevy_bridge_port,
        sketchfab_token=env.get(SKETCHFAB_TOKEN_ENV) or None,
        coral_model_dir=coral_model_dir,
        coral_model=args.coral_model,
        station=args.station,
        station_app=args.station_app,
        station_env=args.station_env,
        station_idle_s=args.station_idle_s,
        station_prompt=args.station_prompt,
        survey_token=survey_token(None, env),
        access_code=env.get(ACCESS_CODE_ENV, "").strip() or None,
        web_dist=args.web_dist,
        read_roots=tuple(
            Path(root) for root in env.get(READ_ROOTS_ENV, "").split(os.pathsep) if root.strip()
        ),
        max_inline_output_bytes=_inline_limit(env),
    )


def _inline_limit(env: Mapping[str, str]) -> int:
    """`max_inline_output_bytes` from the environment, or the default when it is unset."""
    raw = env.get(MAX_INLINE_OUTPUT_ENV, "").strip()
    if not raw:
        return DEFAULT_MAX_INLINE_BYTES
    try:
        limit = int(raw)
    except ValueError:
        limit = 0
    if limit < 1:
        raise ValueError(f"{MAX_INLINE_OUTPUT_ENV} must be a positive integer, not {raw!r}")
    return limit


async def serve(config: AgentServerConfig) -> None:
    """Serve the agent on `config.host:config.port` until cancelled; always stop the host."""
    station = build_station(config)
    workspace = build_demo_workspace(config, station)
    simulation = build_simulation_rig(config)
    description = build_agent_description(
        config,
        workspace=workspace,
        geometry=workspace.geometry,
        simulation=simulation,
        station=station,
    )
    host = HypercornHost(description, None, host=config.host, port=config.port)
    ticker = IdleTicker(station) if station is not None else None
    ports = await host.start()
    bridge = (
        await start_bevy_bridge(config, simulation, station)
        if config.bevy_bridge_port is not None
        else None
    )
    if ticker is not None:
        ticker.start()
    print(f"survey agent on http://{config.host}:{ports.public}", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        if bridge is not None:
            await bridge.aclose()
        if ticker is not None and station is not None:
            ticker.stop()
            await asyncio.to_thread(station.stop)
        await host.stop()


def configure_logging() -> None:
    """INFO and above to stderr, `<time> <level> <logger> <line>`: the event log
    (`surmap.agent.event_log`) is what `modal app logs surmap-agent | grep event=…` reads."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line and serve until signalled; Ctrl-C stops it cleanly — `serve`
    has already stopped the host when `asyncio.run` re-raises the interrupt. The project `.env`
    fills environment gaps first (keys only; a shell export wins)."""
    load_env()
    configure_logging()
    config = config_from_args(argv)
    try:
        asyncio.run(serve(config))
    except KeyboardInterrupt:
        print("survey agent stopped", flush=True)


if __name__ == "__main__":
    main()
