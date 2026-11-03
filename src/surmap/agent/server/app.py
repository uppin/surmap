"""The agent server's configuration and the `ServerDescription` that wires it together.

`build_agent_description` mounts, on one `ChatHub`:

- `ChatService` (`chat_handlers`) and `AgentJobs` (`agent_jobs_handlers`);
- `SurveyTools`, served from the same handlers the agent's tools are bound to, so the UI can
  call a tool directly;
- the HTTP routes (`agent_http_routes`), with CORS for `cors_origins` on every response —
  Connect responses included;
- the hub as a closeable, so stopping the host cancels every turn and ends every watch stream.

Each conversation's tools are `agent_tools` over the `SurveyTools` and `AgentJobs` contracts.
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
from surmap.agent.proto import jobs_pb2, survey_tools_pb2
from surmap.agent.runtime.graph import TurnCaps
from surmap.agent.server.binding import agent_tools
from surmap.agent.server.chat_service import agent_jobs_handlers, chat_handlers
from surmap.agent.server.hub import ChatHub, ModelFactory
from surmap.agent.server.routes import GlbReader, agent_http_routes
from surmap.agent.services import (
    Handler,
    agent_jobs_module,
    chat_service_module,
    survey_tools_module,
)
from surmap.agent.tools.geometry import GeometryStore
from surmap.agent.tools.handlers import survey_tool_handlers
from surmap.agent.tools.workspace import DemoWorkspace, SurveyWorkspace
from surmap.demo.datasets import default_cache_dir
from surmap.demo.runs import DemoRunHost
from surmap.demo.server import make_demo_server
from surmap.rpc.description import ServerDescription
from surmap.survey.sam import CentredBoxVideoSamDetector
from surmap.usage import UsageLedger

_SURVEY_TOOLS = survey_tools_pb2.DESCRIPTOR.services_by_name["SurveyTools"]
_AGENT_JOBS = jobs_pb2.DESCRIPTOR.services_by_name["AgentJobs"]
"""The two tool services; their rpcs are the tools a conversation binds."""

__all__ = [
    "CORS_ORIGINS_ENV",
    "DEFAULT_CORS_ORIGINS",
    "DEFAULT_HOST",
    "DEFAULT_MODEL_ID",
    "DEFAULT_PORT",
    "SYSTEM_PROMPT",
    "AgentServerConfig",
    "build_agent_description",
    "build_demo_workspace",
    "default_model_factory",
]

DEFAULT_HOST = "127.0.0.1"
"""Loopback: the tools start demo runs, so exposing the server takes a deliberate `--host`."""
DEFAULT_PORT = 8780
DEFAULT_MODEL_ID = f"{META_PROVIDER}:{DEFAULT_AGENT_META_MODEL}"
CORS_ORIGINS_ENV = "SURMAP_AGENT_CORS_ORIGINS"
"""Comma-separated origins allowed to call the server from a browser."""
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)
"""The Vite dev server of the chat UI."""

SYSTEM_PROMPT = """\
You are SurMap's survey assistant. You run the survey demos and inspect their results with \
your tools: scenes and runs, SAM prompts, the objects a run reconstructed, their geometry, and \
frames. You only launch demos and read results; you never command a vehicle.

Some tools run as jobs. When a tool call returns a job handle instead of a result, say that \
the job started and name its job id, for example "run_demo started as job j-2". Never say a \
job finished until you have its result. When your next step needs a job's result, call \
wait_for_jobs with its id; otherwise answer and let the job report back when it ends.

When the person steers you mid-turn, the calls that were blocking keep running as jobs; act on \
the new guidance first, and cancel_job a job they no longer want.
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
    timeout_scale: float = 1.0
    """Seconds one execution-policy `timeout_s` unit lasts; 1.0 outside tests."""
    model_factory: ModelFactory | None = None
    """Builds models instead of the registry; the seam tests inject a scripted model through."""


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
    )


def build_agent_description(
    config: AgentServerConfig,
    *,
    workspace: SurveyWorkspace,
    geometry: GlbReader,
    registry: ChatModelRegistry | None = None,
    survey_handlers: Mapping[str, Handler] | None = None,
) -> ServerDescription[None]:
    """The agent server over `workspace`.

    `survey_handlers` defaults to `survey_tool_handlers(workspace)`; `registry` to one over the
    process environment, which also lists the models.
    """
    ledger = UsageLedger()
    models = registry if registry is not None else ChatModelRegistry()
    model_factory = (
        config.model_factory
        if config.model_factory is not None
        else default_model_factory(models, ledger)
    )
    rpc_handlers: dict[str, Handler] = (
        dict(survey_handlers)
        if survey_handlers is not None
        else dict(survey_tool_handlers(workspace))
    )
    contracts = (*tool_contracts(_SURVEY_TOOLS), *tool_contracts(_AGENT_JOBS))
    hub = ChatHub(
        model_factory=model_factory,
        tools=lambda runner: agent_tools(contracts, rpc_handlers, runner),
        models=models.available,
        default_model_id=config.model_id,
        system_prompt=SYSTEM_PROMPT,
        caps=TurnCaps.from_env(os.environ),
        timeout_scale=config.timeout_scale,
    )
    origins = tuple(config.cors_origins)
    return ServerDescription(
        services=(
            survey_tools_module(_allowing_origins(rpc_handlers, origins)),
            agent_jobs_module(_allowing_origins(agent_jobs_handlers(hub), origins)),
            chat_service_module(_allowing_origins(chat_handlers(hub), origins)),
        ),
        http_routes=agent_http_routes(workspace, geometry, cors_origins=origins),
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
