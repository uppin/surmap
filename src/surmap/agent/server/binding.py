"""The tools a conversation binds: the `SurveyTools` handlers and the job tools, over its runner.

A `SurveyTools` handler speaks protos in connect-python's `(request, ctx)` shape. Bound as a
tool, a call's JSON arguments (without `execution`) decode into the rpc's request message, the
handler runs with no request context, and its response comes back as the JSON object
`json_format.MessageToDict` makes of it (proto field names, defaults included). A `bytes` field
named `image` does not go into the JSON: it comes back as a `ToolImage` under `IMAGE_KEY`, which
the model reads as a one-line placeholder and the chat stream carries as image bytes. A
`ConnectError` from the handler, or arguments the request message cannot hold, fail the call.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from surmap.agent.contracts import ToolContract, resolve_execution
from surmap.agent.runtime.jobs import JobRunner
from surmap.agent.runtime.tools import BoundTool, ExecutionResolver
from surmap.agent.services import Handler

__all__ = ["IMAGE_KEY", "ToolImage", "agent_tools"]

IMAGE_KEY = "image"
"""Where a bound tool's result carries the image its response returned."""


@dataclass(frozen=True)
class ToolImage:
    """An image a tool returned, kept out of the JSON the model reads."""

    data: bytes
    media_type: str

    def __str__(self) -> str:
        """What the model reads in place of the bytes, e.g.
        `"<image/jpeg, 48213 bytes, shown to the user>"`."""
        raise NotImplementedError  # TODO(pr-8): implement


def agent_tools(
    contracts: Sequence[ToolContract],
    handlers: Mapping[str, Handler],
    runner: JobRunner,
    *,
    resolve: ExecutionResolver = resolve_execution,
) -> tuple[BoundTool, ...]:
    """Every contract as a tool over `runner`.

    `SurveyTools` contracts are bound to `handlers` by rpc name; `AgentJobs` contracts become
    the four job tools (`surmap.agent.runtime.tools.job_tools`). Raises `ValueError` for a
    `SurveyTools` contract no handler serves.
    """
    raise NotImplementedError  # TODO(pr-8): implement
