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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from langchain_core.language_models import BaseChatModel

from surmap.agent.contracts import tool_contracts
from surmap.agent.event_log import log_event
from surmap.agent.files import file_tools
from surmap.agent.llm.fireworks import FireworksChatModel
from surmap.agent.llm.meta import DEFAULT_AGENT_META_MODEL, META_PROVIDER, MetaResponsesChatModel
from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.proto import (
    fleet_tools_pb2,
    jobs_pb2,
    map_tools_pb2,
    simulation_tools_pb2,
    station_tools_pb2,
    survey_tools_pb2,
)
from surmap.agent.runtime.graph import TurnCaps
from surmap.agent.runtime.outputs import DEFAULT_MAX_INLINE_BYTES, ToolOutputs
from surmap.agent.runtime.session import SqliteConversationStore
from surmap.agent.server.access import UNAUTHENTICATED_HINT, AccessGate, session_token
from surmap.agent.server.binding import agent_tools
from surmap.agent.server.chat_service import agent_jobs_handlers, chat_handlers
from surmap.agent.server.fleet_routes import fleet_websocket_route
from surmap.agent.server.hub import ChatHub, ModelFactory
from surmap.agent.server.routes import GlbReader, agent_http_routes
from surmap.agent.server.sim_routes import SimulationRig
from surmap.agent.services import (
    Handler,
    agent_jobs_module,
    chat_service_module,
    fleet_module,
    map_tools_module,
    simulation_tools_module,
    station_tools_module,
    survey_tools_module,
)
from surmap.agent.skills import SkillCatalogue, skill_tools
from surmap.agent.subagents import SubagentSetup
from surmap.agent.tools.fleet_handlers import drone_map_status_handler, fleet_tool_handlers
from surmap.agent.tools.geometry import GeometryStore
from surmap.agent.tools.handlers import survey_tool_handlers
from surmap.agent.tools.map_handlers import MapSceneStore, map_tool_handlers
from surmap.agent.tools.onboard import ONBOARD_OFF, OnboardModels
from surmap.agent.tools.simulation_handlers import simulation_tool_handlers
from surmap.agent.tools.station import DEFAULT_IDLE_TIMEOUT_S, StationControl, StubStationControl
from surmap.agent.tools.station_handlers import station_tool_handlers
from surmap.agent.tools.station_modal import (
    ModalFunction,
    ModalStationControl,
    http_health_probe,
    modal_station_function,
)
from surmap.agent.tools.workspace import DemoWorkspace, SurveyWorkspace
from surmap.demo.datasets import default_cache_dir
from surmap.demo.remote import RemoteSamDetector
from surmap.demo.runs import DemoRunHost
from surmap.demo.server import make_demo_server
from surmap.detection import DEFAULT_PROFILE
from surmap.rpc.description import ServerDescription
from surmap.simulation.asset_sources import AmbientCg, AssetSource, PolyHaven, Sketchfab, http_fetch
from surmap.simulation.bevy_bridge import StreamingBackend, serve_bevy_bridge
from surmap.simulation.fleet.perception import (
    FleetPerception,
    SamSegmentationSink,
    SegmentationFactory,
)
from surmap.simulation.scenario_manifest import load_presets
from surmap.simulation.scenario_store import ScenarioStore
from surmap.slam.streaming import StreamingRtabmapBackend
from surmap.survey.modal_hosting import STATION_APP_NAME
from surmap.survey.sam import CentredBoxVideoSamDetector, VideoAsFrameSamDetector, VideoSamDetector
from surmap.usage import UsageLedger, default_usage_log_path

_SURVEY_TOOLS = survey_tools_pb2.DESCRIPTOR.services_by_name["SurveyTools"]
_MAP_TOOLS = map_tools_pb2.DESCRIPTOR.services_by_name["MapTools"]
_SIMULATION_TOOLS = simulation_tools_pb2.DESCRIPTOR.services_by_name["SimulationTools"]
_STATION_TOOLS = station_tools_pb2.DESCRIPTOR.services_by_name["StationTools"]
_FLEET_TOOLS = fleet_tools_pb2.DESCRIPTOR.services_by_name["FleetTools"]
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
    "conversation_store",
    "default_model_factory",
    "default_state_dir",
    "map_scene_store",
    "onboard_models",
    "tool_outputs",
    "usage_log_path",
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
READ_ROOTS_ENV = "SURMAP_AGENT_READ_ROOTS"
"""Folders (`os.pathsep`-separated) read_file and grep_files may read beside the saved outputs."""
MAX_INLINE_OUTPUT_ENV = "SURMAP_AGENT_MAX_INLINE_OUTPUT_BYTES"
"""Bytes of JSON a tool result may be before it is saved to a file instead of sent inline."""
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
Builds are cached by key (mode, SAM prompt, on-board model, frame limit): run_demo and \
run_rtabmap answer from a dataset's cached run with the same key, marked cached, unless asked \
to rebuild. list_runs lists a dataset's runs (its cached builds) and run_cached runs one; say \
when an answer came from a cached run. \
You also edit \
the display map: place and move GLB shapes with the map tools, navigate \
its camera, and draw route paths. Map edits change only what the person sees; routes are drawn \
paths, never flight plans. Simulated drones in the station's simulation can be tasked with the \
fleet tools. Real aircraft are never commanded. You otherwise only launch demos and read results.

Some tools run as jobs. When a tool call returns a job handle instead of a result, say that \
the job started and name its job id, for example "run_demo started as job j-2". Never say a \
job finished until you have its result. When your next step needs a job's result, call \
wait_for_jobs with its id; otherwise answer and let the job report back when it ends.

A tool result too big for the conversation comes back as a saved file's path with a preview \
instead; any tool call can also ask for that with output: {"to_file": true}. Read such a file \
with read_file and search it with grep_files, rather than asking for the whole result again.

When the person steers you mid-turn, the calls that were blocking keep running as jobs; act on \
the new guidance first, and cancel_job a job they no longer want.

You also have skills: reviewed instructions for kinds of work. Call list_skills to see \
them, and load_skill to read the one that fits the task before you start it — in \
particular, load the map skill before placing, moving or drawing anything on the map, and the \
simulation skill before creating or changing a simulation scene, and the fleet skill before \
tasking a simulated drone.

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
stopped. Use message_main_agent only for something it must know while you keep working. The \
person follows your task in a tasks panel: call report_status when you start, and again at each \
major step, with what you are doing now in a few words (e.g. "Placing the house"). Guidance \
from the main agent can arrive while you work; act on it first. Wait for any job you started \
before you answer. A result too big for your context comes back as a saved file's path; read \
or search it with read_file and grep_files. You only build and read; you never command a vehicle.
"""


@dataclass(frozen=True)
class AgentServerConfig:
    """How `python -m surmap.agent` runs."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    state_dir: Path | None = None
    """Where the agent keeps what a conversation leaves behind, so a restart over it brings the
    chat back: `conversations.sqlite`, `map-scenes.sqlite`, `demo-history.db`, `simulation/`,
    `agent-tool-outputs/`, `agent-geometry/`, `usage.jsonl`; a store's own setting wins. The
    command line always sets it (default: the cache root). None keeps conversations and the map
    scene in memory and the rest under the cache, as tests and embedders build it."""
    history_db: Path | None = None
    """The demo run history; `<state_dir>/demo-history.db`, else `<cache_dir>/demo-history.db`."""
    conversations_db: Path | None = None
    """The chat conversations (history, model, replay) in SQLite;
    `<state_dir>/conversations.sqlite`, else in memory."""
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
    tool_outputs_dir: Path | None = None
    """Where large or requested tool results are saved, a folder per conversation;
    `<state_dir>/agent-tool-outputs`, else `<cache_dir>/agent-tool-outputs`."""
    max_inline_output_bytes: int = DEFAULT_MAX_INLINE_BYTES
    """Bytes of JSON a tool result may be before it is saved instead; the command line fills it
    from `$SURMAP_AGENT_MAX_INLINE_OUTPUT_BYTES`."""
    read_roots: tuple[Path, ...] = ()
    """Folders read_file and grep_files may read beside a conversation's saved outputs; the
    command line fills it from `$SURMAP_AGENT_READ_ROOTS`."""
    model_factory: ModelFactory | None = None
    """Builds models instead of the registry; the seam tests inject a scripted model through."""
    sim_dir: Path | None = None
    """The simulation store (`simulation.sqlite` + `library/`); `<state_dir>/simulation`, else
    `<cache>/simulation`."""
    sim_assets: Path = Path("examples/bevy-sitl-poc/assets")
    """The Bevy simulation's own assets; simulation tools are off when it is missing."""
    sim_dist: Path | None = None
    """A built simulation page to serve at `/sim/`."""
    bevy_bridge_port: int | None = None
    """Serve the stereo bridge a `?bridge=` simulation page streams to on this port (each drone
    into its own streaming RTAB-Map, segmented with the configured SAM); None: no bridge."""
    sketchfab_token: str | None = None
    """`SKETCHFAB_API_TOKEN`: Sketchfab search works without it, downloads do not."""
    coral_model_dir: Path | None = None
    """The prepared Coral model dir (`scripts/fetch_coral_model.py`); none: no on-board model."""
    coral_model: str = DEFAULT_PROFILE
    """The on-board model a run that names none uses; `"none"` for no on-board model."""
    station: str | None = None
    """The SAM station the agent's SAM runs on: `"modal"`, `"stub"`, or None for none."""
    station_app: str = STATION_APP_NAME
    """The deployed Modal app of a `"modal"` station."""
    station_env: str | None = None
    """The Modal environment of that app; None: the profile's default."""
    station_idle_s: int = DEFAULT_IDLE_TIMEOUT_S
    """Seconds without a SAM frame after which the agent stops the station."""
    station_prompt: str = "object"
    """The SAM concept a station link starts with; each run's prompt replaces it."""
    survey_token: str | None = None
    """`SURMAP_SURVEY_TOKEN`: the bearer token the station's Connect calls carry."""
    access_code: str | None = None
    """`SURMAP_AGENT_ACCESS_CODE`: the pass code every caller signs in with; None: no gate."""
    web_dist: Path | None = None
    """A built chat page (`web/agent-chat/dist`) served at `/`."""


DEFAULT_SIM_ASSETS = Path("examples/bevy-sitl-poc/assets")
SKETCHFAB_TOKEN_ENV = "SKETCHFAB_API_TOKEN"


def build_simulation_rig(config: AgentServerConfig) -> SimulationRig | None:
    """The store, live sources and paths behind the simulation tools, or None when the
    simulation's assets are not where `config.sim_assets` says."""
    if not (config.sim_assets / "scene.json").is_file():
        return None
    root = config.sim_dir or _state_root(config) / "simulation"
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


class Closeable(Protocol):
    """A running service the agent stops on its way out."""

    async def aclose(self) -> None: ...


async def start_bevy_bridge(
    config: AgentServerConfig,
    simulation: SimulationRig | None,
    station: StationControl | None = None,
) -> Closeable:
    """The stereo bridge on `config.host:config.bevy_bridge_port`: a `FleetPerception` per page
    connection over the streaming RTAB-Map factory and the agent's SAM (`bridge_segmentation`: the
    station's, else the fake with `--sam-fake`), registered
    in `simulation.perception` so `drone_map_status` finds it. Closing it stops serving."""
    if config.bevy_bridge_port is None:
        raise ValueError("start_bevy_bridge needs config.bevy_bridge_port")
    segmentation = bridge_segmentation(config, station)

    def backend_factory(
        *, cam0_yaml: str, cam1_yaml: str, width: int, height: int
    ) -> StreamingBackend:
        return cast(
            "StreamingBackend",
            StreamingRtabmapBackend(
                cam0_yaml=cam0_yaml, cam1_yaml=cam1_yaml, width=width, height=height
            ),
        )

    def session_factory() -> FleetPerception:
        return FleetPerception(
            backend_factory,
            segmentation,
            registry=simulation.perception if simulation is not None else None,
        )

    server = await serve_bevy_bridge(config.host, config.bevy_bridge_port, session_factory)

    class _Bridge:
        async def aclose(self) -> None:
            server.close()
            await server.wait_closed()

    return _Bridge()


def bridge_segmentation(
    config: AgentServerConfig, station: StationControl | None = None
) -> SegmentationFactory:
    """The stereo bridge's segmentation: a `SamSegmentationSink` per drone session, each on its
    own video of the agent's SAM (`agent_sam`: the station's, else the fake with `--sam-fake`,
    else a refusal)."""
    agent_sam(config, station)  # refuse now, not on the first drone's first frame

    def segmentation(_drone_id: str) -> SamSegmentationSink:
        return SamSegmentationSink(VideoAsFrameSamDetector(agent_sam(config, station)))

    return segmentation


def agent_sam(config: AgentServerConfig, station: StationControl | None) -> VideoSamDetector:
    """A SAM for one video the agent runs: `station`'s detector when there is a station, else the
    fake centred-box SAM with `--sam-fake`; neither is a refusal."""
    if station is not None:
        return station.detector()
    if config.sam_fake:
        return CentredBoxVideoSamDetector()
    raise ValueError(
        "the agent needs a SAM: pass --station modal|stub to run it on a station, "
        "or --sam-fake for the fake centred-box SAM"
    )


def _cache_root(config: AgentServerConfig) -> Path:
    if config.cache_dir is not None:
        return config.cache_dir
    return default_state_dir(os.environ)


def default_state_dir(environ: Mapping[str, str]) -> Path:
    """The cache root, where the command line keeps the agent's state when it names no dir:
    `$SURMAP_DEMO_CACHE_DIR` or `~/.cache/surmap`."""
    return Path(environ.get("SURMAP_DEMO_CACHE_DIR", Path.home() / ".cache" / "surmap"))


def _state_root(config: AgentServerConfig) -> Path:
    return config.state_dir if config.state_dir is not None else _cache_root(config)


def tool_outputs(config: AgentServerConfig) -> ToolOutputs:
    """The root the server's conversations save large or requested tool results under."""
    directory = config.tool_outputs_dir or _state_root(config) / "agent-tool-outputs"
    return ToolOutputs(directory=directory, max_inline_bytes=config.max_inline_output_bytes)


def conversation_store(config: AgentServerConfig) -> SqliteConversationStore | None:
    """The SQLite conversation store for `config.conversations_db`, else in the state dir, or
    None to keep conversations in memory (a config with neither)."""
    if config.conversations_db is not None:
        return SqliteConversationStore(config.conversations_db)
    if config.state_dir is not None:
        return SqliteConversationStore(config.state_dir / "conversations.sqlite")
    return None


def map_scene_store(config: AgentServerConfig) -> MapSceneStore:
    """The map scenes, saved in the state dir; in memory without one."""
    if config.state_dir is None:
        return MapSceneStore()
    return MapSceneStore(db_path=config.state_dir / "map-scenes.sqlite")


def usage_log_path(config: AgentServerConfig) -> Path:
    """Where the server's usage ledger writes: `$SURMAP_USAGE_LOG` when set, else
    `<state_dir>/usage.jsonl`, else `<cache_dir>/usage.jsonl` when a cache dir is configured
    (on Modal that is the Volume, so budgets survive a restart), else the home default."""
    if os.environ.get("SURMAP_USAGE_LOG", "").strip():
        return default_usage_log_path()
    if config.state_dir is not None:
        return config.state_dir / "usage.jsonl"
    if config.cache_dir is not None:
        return config.cache_dir / "usage.jsonl"
    return default_usage_log_path()


def default_model_factory(registry: ChatModelRegistry, ledger: UsageLedger) -> ModelFactory:
    """Models from `registry`; a `meta:` or `fireworks:` model checks `ledger` before every
    request and records its usage there."""

    def build(model_id: str) -> BaseChatModel:
        model = registry.build(model_id)
        if isinstance(model, MetaResponsesChatModel | FireworksChatModel):
            return model.model_copy(update={"before_call": ledger.check, "usage_sink": ledger})
        return model

    return build


def build_station(
    config: AgentServerConfig,
    *,
    modal_function: Callable[[str, str | None], ModalFunction] = modal_station_function,
) -> StationControl | None:
    """The configured SAM station, or None; `modal_function` looks the deployed app up."""
    if config.station is None:
        return None
    if config.station == "stub":
        return StubStationControl(idle_timeout_s=config.station_idle_s)
    if config.station != "modal":
        raise ValueError(f"unknown station {config.station!r}: use modal or stub")
    environment = config.station_env
    return ModalStationControl(
        modal_function(config.station_app, environment),
        probe=http_health_probe,
        connect=_station_link,
        token=config.survey_token,
        prompt=config.station_prompt,
        idle_timeout_s=config.station_idle_s,
        backend=f"modal:{environment or 'main'}/{config.station_app}",
    )


def _station_link(url: str, token: str | None, prompt: str) -> VideoSamDetector:
    return RemoteSamDetector(url, prompt=prompt, token=token)


def build_demo_workspace(
    config: AgentServerConfig, station: StationControl | None = None
) -> DemoWorkspace:
    """A `DemoWorkspace` over a non-serving demo run host on the configured cache and history.

    Its SAM runs on `station` when there is one, else the fake SAM with `--sam-fake`.
    """
    detector = agent_sam(config, station)
    cache_dir = config.cache_dir if config.cache_dir is not None else default_cache_dir()
    state_dir = config.state_dir if config.state_dir is not None else cache_dir
    history_db = config.history_db
    if history_db is None and config.state_dir is not None:
        history_db = config.state_dir / "demo-history.db"
    server = make_demo_server(
        None,
        cache_dir=cache_dir,
        history_db=history_db,
        port=0,
        with_rtabmap=False,
        sam_fake=True,
    )
    if not isinstance(server, DemoRunHost):
        raise TypeError("the demo server is not a run host")
    return DemoWorkspace(
        server,
        detector=detector,
        geometry=GeometryStore(state_dir / "agent-geometry"),
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
    station: StationControl | None = None,
) -> ServerDescription[None]:
    """The agent server over `workspace`.

    `survey_handlers` defaults to `survey_tool_handlers(workspace)`; `registry` to one over the
    process environment, which also lists the models. With `simulation`, the `SimulationTools`
    and `FleetTools` are mounted and bound as agent tools, `/sim/` serves the page, scenarios
    and library, and `/sim/fleet` links a running page to the station's fleet controllers.
    With `station`, the `StationTools` are mounted and bound the same way.
    """
    ledger = UsageLedger(usage_log_path(config))
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
    map_handlers: dict[str, Handler] = dict(map_tool_handlers(map_scene_store(config)))
    sim_handlers: dict[str, Handler] = (
        dict(simulation_tool_handlers(simulation.store, simulation.sources))
        if simulation is not None
        else {}
    )
    fleet_handlers: dict[str, Handler] = (
        {
            **fleet_tool_handlers(simulation.store, simulation.fleet),
            "DroneMapStatus": drone_map_status_handler(simulation.store, simulation.perception),
        }
        if simulation is not None
        else {}
    )
    station_handlers: dict[str, Handler] = (
        dict(station_tool_handlers(station)) if station is not None else {}
    )
    rpc_handlers: dict[str, Handler] = {
        **survey_only,
        **map_handlers,
        **sim_handlers,
        **fleet_handlers,
        **station_handlers,
    }
    contracts = (
        *tool_contracts(_SURVEY_TOOLS),
        *tool_contracts(_MAP_TOOLS),
        *(tool_contracts(_SIMULATION_TOOLS) if simulation is not None else ()),
        *(tool_contracts(_FLEET_TOOLS) if simulation is not None else ()),
        *(tool_contracts(_STATION_TOOLS) if station is not None else ()),
        *tool_contracts(_AGENT_JOBS),
    )
    catalogue = SkillCatalogue.shipped(config.skills_dir)
    hub = ChatHub(
        model_factory=model_factory,
        tools=lambda runner: (
            *agent_tools(contracts, rpc_handlers, runner),
            *skill_tools(catalogue, runner),
            *file_tools(runner, extra_roots=config.read_roots),
        ),
        models=models.available,
        default_model_id=config.model_id,
        system_prompt=SYSTEM_PROMPT,
        caps=TurnCaps.from_env(os.environ),
        timeout_scale=config.timeout_scale,
        subagents=SubagentSetup(system_prompt=SUBAGENT_PROMPT, load_skill=catalogue.load_skill),
        store=conversation_store(config),
        outputs=tool_outputs(config),
    )
    origins = tuple(config.cors_origins)
    gate = AccessGate(config.access_code) if config.access_code else None

    def guarded(handlers: Mapping[str, Handler]) -> dict[str, Handler]:
        return _requiring_session(_allowing_origins(handlers, origins), gate)

    return ServerDescription(
        services=(
            survey_tools_module(guarded(survey_only)),
            map_tools_module(guarded(map_handlers)),
            *(
                (
                    simulation_tools_module(guarded(sim_handlers)),
                    fleet_module(guarded(fleet_handlers)),
                )
                if simulation is not None
                else ()
            ),
            *((station_tools_module(guarded(station_handlers)),) if station is not None else ()),
            agent_jobs_module(guarded(agent_jobs_handlers(hub))),
            chat_service_module(guarded(chat_handlers(hub))),
        ),
        http_routes=agent_http_routes(
            workspace,
            geometry,
            cors_origins=origins,
            datasets=workspace,
            simulation=simulation,
            gate=gate,
            web_dist=config.web_dist,
        ),
        websocket_routes=(fleet_websocket_route(simulation),) if simulation is not None else (),
        closeables=lambda _context: (hub,),
    )


def _requiring_session(
    handlers: Mapping[str, Handler], gate: AccessGate | None
) -> dict[str, Handler]:
    """`handlers`, each refusing a call with no valid session token when there is a `gate`."""
    if gate is None:
        return dict(handlers)
    return {name: _with_session(name, handler, gate) for name, handler in handlers.items()}


def _with_session(name: str, handler: Handler, gate: AccessGate) -> Handler:
    def serve(request: object, ctx: RequestContext[Any, Any]) -> Any:
        headers = {key.lower(): value for key, value in ctx.request_headers.items()}
        token = session_token(headers)
        if token is None or not gate.allows(token):
            log_event("auth_refused", surface="rpc", target=name)
            raise ConnectError(Code.UNAUTHENTICATED, UNAUTHENTICATED_HINT)
        return handler(request, ctx)

    return serve


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
