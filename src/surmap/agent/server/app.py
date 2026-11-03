"""The agent server's configuration and the `ServerDescription` that wires it together.

`build_agent_description` mounts, on one `ChatHub`:

- `ChatService` (`chat_handlers`) and `AgentJobs` (`agent_jobs_handlers`);
- `SurveyTools`, served from the same handlers the agent's tools are bound to, so the UI can
  call a tool directly;
- the HTTP routes (`agent_http_routes`), with CORS for `cors_origins` on every response —
  Connect responses included;
- the hub as a closeable, so stopping the host cancels every turn and ends every watch stream.

Each conversation's tools are `agent_tools` over the `SurveyTools` and `AgentJobs` contracts.
Models come from `config.model_factory`, or else from the registry: a `meta:` model gets the
process's `UsageLedger.check` as its `before_call`, so a spent budget refuses the request before
it is sent. Binds loopback by default; there is no auth (docs/agent.md).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from surmap.agent.llm.meta import DEFAULT_AGENT_META_MODEL, META_PROVIDER
from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.server.hub import ModelFactory
from surmap.agent.server.routes import GlbReader
from surmap.agent.services import Handler
from surmap.agent.tools.workspace import DemoWorkspace, SurveyWorkspace
from surmap.rpc.description import ServerDescription
from surmap.usage import UsageLedger

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
    """Models from `registry`; a `meta:` model checks `ledger` before every request."""
    raise NotImplementedError  # TODO(pr-8): implement


def build_demo_workspace(config: AgentServerConfig) -> DemoWorkspace:
    """A `DemoWorkspace` over a non-serving demo run host on the configured cache and history."""
    raise NotImplementedError  # TODO(pr-8): implement


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
    raise NotImplementedError  # TODO(pr-8): implement
