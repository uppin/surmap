"""The agent server's configuration and the `ServerDescription` that wires it together.

`build_agent_description` mounts, on one `ChatHub`:

- `ChatService` (`chat_handlers`) and `AgentJobs` (`agent_jobs_handlers`);
- `SurveyTools`, served from the same handlers the agent's tools are bound to, so the UI can
  call a tool directly;
- the HTTP routes (`agent_http_routes`), with CORS for `cors_origins` on every response —
  Connect responses included;
- the hub as a closeable, so stopping the host cancels every turn and ends every watch stream.

Each conversation's tools are `agent_tools` over the `SurveyTools` and `AgentJobs` contracts,
the skill tools, and the subagent tools; a subagent starts from `SUBAGENT_PROMPT` and a shipped
skill.
Models come from `config.model_factory`, or else from the registry: a `meta:` or `fireworks:`
model gets the process's `UsageLedger.check` as its `before_call` (so a spent budget refuses the
request before it is sent) and the ledger as its `usage_sink`. Binds loopback by default; there
is no auth (docs/agent.md).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from connectrpc.request import RequestContext
from langchain_core.language_models import BaseChatModel

from surmap.agent.contracts import tool_contracts
from surmap.agent.llm.fireworks import FireworksChatModel
from surmap.agent.llm.meta import DEFAULT_AGENT_META_MODEL, META_PROVIDER, MetaResponsesChatModel
from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.proto import jobs_pb2, map_tools_pb2, simulation_tools_pb2, survey_tools_pb2
from surmap.agent.runtime.graph import TurnCaps
from surmap.agent.server.binding import agent_tools
from surmap.agent.server.chat_service import agent_jobs_handlers, chat_handlers
from surmap.agent.server.hub import ChatHub, ModelFactory
from surmap.agent.server.routes import GlbReader, agent_http_routes
from surmap.agent.server.sim_routes import SimulationRig
from surmap.agent.services import (
    Handler,
    agent_jobs_module,
    chat_service_module,
    map_tools_module,
    simulation_tools_module,
    survey_tools_module,
)
from surmap.agent.skills import SkillCatalogue, skill_tools
from surmap.agent.subagents import SubagentSetup
from surmap.agent.tools.geometry import GeometryStore
from surmap.agent.tools.handlers import survey_tool_handlers
from surmap.agent.tools.map_handlers import MapSceneStore, map_tool_handlers
from surmap.agent.tools.onboard import ONBOARD_OFF, OnboardModels
from surmap.agent.tools.simulation_handlers import simulation_tool_handlers
from surmap.agent.tools.workspace import DemoWorkspace, SurveyWorkspace
from surmap.demo.datasets import default_cache_dir
from surmap.demo.runs import DemoRunHost
from surmap.demo.server import make_demo_server
from surmap.detection import DEFAULT_PROFILE
from surmap.rpc.description import ServerDescription
from surmap.simulation.asset_sources import AmbientCg, AssetSource, PolyHaven, Sketchfab, http_fetch
from surmap.simulation.scenario_manifest import load_presets
from surmap.simulation.scenario_store import ScenarioStore
from surmap.survey.sam import CentredBoxVideoSamDetector
from surmap.usage import UsageLedger

_SURVEY_TOOLS = survey_tools_pb2.DESCRIPTOR.services_by_name["SurveyTools"]
_MAP_TOOLS = map_tools_pb2.DESCRIPTOR.services_by_name["MapTools"]
_SIMULATION_TOOLS = simulation_tools_pb2.DESCRIPTOR.services_by_name["SimulationTools"]
_AGENT_JOBS = jobs_pb2.DESCRIPTOR.services_by_name["AgentJobs"]
"""The three tool services; their rpcs are the tools a conversation binds."""

__all__ = [
    "CORAL_MODEL_DIR_ENV",
    "CORS_ORIGINS_ENV",
    "DEFAULT_CORS_ORIGINS",
    "DEFAULT_HOST",
    "DEFAULT_MODEL_ID",
    "DEFAULT_PORT",
    "SKILLS_DIR_ENV",
    "SUBAGENT_PROMPT",
    "SYSTEM_PROMPT",
    "AgentServerConfig",
    "build_agent_description",
    "build_demo_workspace",
    "default_model_factory",
    "onboard_models",
]

DEFAULT_HOST = "127.0.0.1"
"""Loopback: the tools start demo runs, so exposing the server takes a deliberate `--host`."""
DEFAULT_PORT = 8780
DEFAULT_MODEL_ID = f"{META_PROVIDER}:{DEFAULT_AGENT_META_MODEL}"
CORS_ORIGINS_ENV = "SURMAP_AGENT_CORS_ORIGINS"
"""Comma-separated origins allowed to call the server from a browser."""
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)
"""The Vite dev server of the chat UI."""
SKILLS_DIR_ENV = "SURMAP_AGENT_SKILLS_DIR"
"""A directory of extra skills (`<name>/SKILL.md`) overlaid on the shipped ones."""
CORAL_MODEL_DIR_ENV = "SURMAP_CORAL_MODEL_DIR"
"""The prepared Coral model dir when `--coral-model-dir` names none, as for `scripts/demo.py`."""

SYSTEM_PROMPT = """\
You are SurMap's survey assistant. You run the survey demos and inspect their results with \
your tools: scenes and runs, SAM prompts, the objects a run reconstructed, their geometry, and \
frames. You also work from the dataset gallery: list_datasets shows every dataset with its \
provider, licence, grey or colour modality and GPS preview data; prepare_dataset downloads \
one, run_rtabmap runs RTAB-Map alone on it, run_sam_on_dataset segments it with SAM alone, \
and run_demo runs both together. Prefer the split tools when the person asks for only \
RTAB-Map or only SAM, and name the dataset's licence when you report a dataset. run_demo and \
run_rtabmap also take an onboard_model: the on-board detector that processes the frames, picked \
from list_onboard_models, or "none" to run without one; leave it out for the station default. \
An on-board model recognises only its listed classes (people and vehicles, not debris, buildings \
or fire); when run_demo says it does not recognise the prompt, only SAM can find it. \
You also edit \
the display map: place and move GLB shapes with the map tools, navigate \
its camera, and draw route paths. Map edits change only what the person sees; routes are drawn \
paths, never flight plans. You only launch demos and read results; you never command a vehicle.

Some tools run as jobs. When a tool call returns a job handle instead of a result, say that \
the job started and name its job id, for example "run_demo started as job j-2". Never say a \
job finished until you have its result. When your next step needs a job's result, call \
wait_for_jobs with its id; otherwise answer and let the job report back when it ends.

When the person steers you mid-turn, the calls that were blocking keep running as jobs; act on \
the new guidance first, and cancel_job a job they no longer want.

You also have skills: reviewed instructions for kinds of work. Call list_skills to see \
them, and load_skill to read the one that fits the task before you start it — in \
particular, load the map skill before placing, moving or drawing anything on the map, and the \
simulation skill before creating or changing a simulation scene.

Work with many steps that the person needs only the outcome of — building a simulation scene is \
the main case — goes to a subagent: start_subagent hands it a complete brief and it works in a \
context of its own. Its messages reach you as notices naming the subagent; answer what it asks \
with message_subagent, and tell the person what it reports when it finishes.
"""

SUBAGENT_PROMPT = """\
You are a subagent of SurMap's survey assistant. The main agent gave you one task; you do it \
alone with your tools, and the person does not see your messages. Your final answer is your \
report to the main agent: short and complete — what you made, the ids it will need, and anything \
left unresolved. Never claim a step you did not verify with a tool result.

When you need a decision only the main agent or the person can make, finish with the question as \
your final answer; the main agent answers with a new message and you continue from where you \
stopped. Use message_main_agent only for something it must know while you keep working. Guidance \
from the main agent can arrive while you work; act on it first. Wait for any job you started \
before you answer. You only build and read; you never command a vehicle.
"""


@dataclass(frozen=True)
class AgentServerConfig:
    """How `python -m surmap.agent` runs."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    history_db: Path | None = None
    """The demo run history; `<cache_dir>/demo-history.db` when None."""
    cache_dir: Path | None = None
    """The demo scene cache; `$SURMAP_DEMO_CACHE_DIR` or `~/.cache/surmap/demo-datasets`."""
    model_id: str = DEFAULT_MODEL_ID
    """The model a turn uses when `StreamTurn` names none."""
    sam_fake: bool = False
    """Use the fake centred-box SAM instead of a real detector."""
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    skills_dir: Path | None = None
    """Extra skills overlaid on the shipped ones; the command line fills it from
    `$SURMAP_AGENT_SKILLS_DIR` (see `surmap.agent.__main__`)."""
    timeout_scale: float = 1.0
    """Seconds one execution-policy `timeout_s` unit lasts; 1.0 outside tests."""
    model_factory: ModelFactory | None = None
    """Builds models instead of the registry; the seam tests inject a scripted model through."""
    sim_dir: Path | None = None
    """The simulation store (`simulation.sqlite` + `library/`); `<cache>/simulation` when None."""
    sim_assets: Path = Path("examples/bevy-sitl-poc/assets")
    """The Bevy simulation's own assets; simulation tools are off when it is missing."""
    sim_dist: Path | None = None
    """A built simulation page to serve at `/sim/`."""
    sketchfab_token: str | None = None
    """`SKETCHFAB_API_TOKEN`: Sketchfab search works without it, downloads do not."""
    coral_model_dir: Path | None = None
    """The prepared Coral model dir (`scripts/fetch_coral_model.py`); none: no on-board model."""
    coral_model: str = DEFAULT_PROFILE
    """The on-board model a run that names none uses; `"none"` for no on-board model."""


DEFAULT_SIM_ASSETS = Path("examples/bevy-sitl-poc/assets")
SKETCHFAB_TOKEN_ENV = "SKETCHFAB_API_TOKEN"


def build_simulation_rig(config: AgentServerConfig) -> SimulationRig | None:
    """The store, live sources and paths behind the simulation tools, or None when the
    simulation's assets are not where `config.sim_assets` says."""
    if not (config.sim_assets / "scene.json").is_file():
        return None
    root = config.sim_dir or _cache_root(config) / "simulation"
    store = ScenarioStore(
        db_path=root / "simulation.sqlite",
        library_dir=root / "library",
        presets=load_presets(config.sim_assets),
        assets_dir=config.sim_assets,
    )
    sources: dict[str, AssetSource] = {
        "polyhaven": PolyHaven(http_fetch),
        "ambientcg": AmbientCg(http_fetch),
        "sketchfab": Sketchfab(http_fetch, token=config.sketchfab_token),
    }
    return SimulationRig(
        store=store, sources=sources, static_assets=config.sim_assets, page_dist=config.sim_dist
    )


def _cache_root(config: AgentServerConfig) -> Path:
    if config.cache_dir is not None:
        return config.cache_dir
    return Path(os.environ.get("SURMAP_DEMO_CACHE_DIR", Path.home() / ".cache" / "surmap"))


def default_model_factory(registry: ChatModelRegistry, ledger: UsageLedger) -> ModelFactory:
    """Models from `registry`; a `meta:` or `fireworks:` model checks `ledger` before every
    request and records its usage there."""

    def build(model_id: str) -> BaseChatModel:
        model = registry.build(model_id)
        if isinstance(model, MetaResponsesChatModel | FireworksChatModel):
            return model.model_copy(update={"before_call": ledger.check, "usage_sink": ledger})
        return model

    return build


def build_demo_workspace(config: AgentServerConfig) -> DemoWorkspace:
    """A `DemoWorkspace` over a non-serving demo run host on the configured cache and history."""
    if not config.sam_fake:
        raise ValueError("the agent process runs the fake SAM only for now: pass --sam-fake")
    cache_dir = config.cache_dir if config.cache_dir is not None else default_cache_dir()
    server = make_demo_server(
        None,
        cache_dir=cache_dir,
        history_db=config.history_db,
        port=0,
        with_rtabmap=False,
        sam_fake=True,
    )
    if not isinstance(server, DemoRunHost):
        raise TypeError("the demo server is not a run host")
    return DemoWorkspace(
        server,
        detector=CentredBoxVideoSamDetector(),
        geometry=GeometryStore(cache_dir / "agent-geometry"),
        onboard=onboard_models(config),
    )


def onboard_models(config: AgentServerConfig) -> OnboardModels:
    """The on-board models in the configured Coral dir; the configured default only with a dir."""
    if config.coral_model_dir is None:
        return OnboardModels()
    default = None if config.coral_model == ONBOARD_OFF else config.coral_model
    return OnboardModels(config.coral_model_dir, default=default)


def build_agent_description(
    config: AgentServerConfig,
    *,
    workspace: SurveyWorkspace,
    geometry: GlbReader,
    registry: ChatModelRegistry | None = None,
    survey_handlers: Mapping[str, Handler] | None = None,
    simulation: SimulationRig | None = None,
) -> ServerDescription[None]:
    """The agent server over `workspace`.

    `survey_handlers` defaults to `survey_tool_handlers(workspace)`; `registry` to one over the
    process environment, which also lists the models. With `simulation`, the `SimulationTools`
    are mounted, bound as agent tools, and `/sim/` serves the page, scenarios and library.
    """
    ledger = UsageLedger()
    models = registry if registry is not None else ChatModelRegistry()
    model_factory = (
        config.model_factory
        if config.model_factory is not None
        else default_model_factory(models, ledger)
    )
    survey_only: dict[str, Handler] = (
        dict(survey_handlers)
        if survey_handlers is not None
        else dict(survey_tool_handlers(workspace))
    )
    map_handlers: dict[str, Handler] = dict(map_tool_handlers(MapSceneStore()))
    sim_handlers: dict[str, Handler] = (
        dict(simulation_tool_handlers(simulation.store, simulation.sources))
        if simulation is not None
        else {}
    )
    rpc_handlers: dict[str, Handler] = {**survey_only, **map_handlers, **sim_handlers}
    contracts = (
        *tool_contracts(_SURVEY_TOOLS),
        *tool_contracts(_MAP_TOOLS),
        *(tool_contracts(_SIMULATION_TOOLS) if simulation is not None else ()),
        *tool_contracts(_AGENT_JOBS),
    )
    catalogue = SkillCatalogue.shipped(config.skills_dir)
    hub = ChatHub(
        model_factory=model_factory,
        tools=lambda runner: (
            *agent_tools(contracts, rpc_handlers, runner),
            *skill_tools(catalogue, runner),
        ),
        models=models.available,
        default_model_id=config.model_id,
        system_prompt=SYSTEM_PROMPT,
        caps=TurnCaps.from_env(os.environ),
        timeout_scale=config.timeout_scale,
        subagents=SubagentSetup(system_prompt=SUBAGENT_PROMPT, load_skill=catalogue.load_skill),
    )
    origins = tuple(config.cors_origins)
    return ServerDescription(
        services=(
            survey_tools_module(_allowing_origins(survey_only, origins)),
            map_tools_module(_allowing_origins(map_handlers, origins)),
            *(
                (simulation_tools_module(_allowing_origins(sim_handlers, origins)),)
                if simulation is not None
                else ()
            ),
            agent_jobs_module(_allowing_origins(agent_jobs_handlers(hub), origins)),
            chat_service_module(_allowing_origins(chat_handlers(hub), origins)),
        ),
        http_routes=agent_http_routes(
            workspace, geometry, cors_origins=origins, datasets=workspace, simulation=simulation
        ),
        closeables=lambda _context: (hub,),
    )


def _allowing_origins(
    handlers: Mapping[str, Handler], origins: tuple[str, ...]
) -> dict[str, Handler]:
    """`handlers`, each adding CORS for `origins` to the Connect response it answers with."""
    return {name: _with_cors(handler, origins) for name, handler in handlers.items()}


def _with_cors(handler: Handler, origins: tuple[str, ...]) -> Handler:
    """`handler` with the response's `Access-Control-Allow-Origin` set when the request's
    `Origin` is one of `origins`; Connect sends the context's response headers first."""

    def serve(request: object, ctx: RequestContext[Any, Any]) -> Any:
        origin = ctx.request_headers.get("origin")
        if origin is not None and origin in origins:
            ctx.response_headers["access-control-allow-origin"] = origin
        return handler(request, ctx)

    return serve
