"""Tools the model binds: a `ToolContract` plus its handler, run through the `JobRunner`.

The policy of each call comes from an injected resolver (`surmap.agent.contracts.resolve_execution`
by default): the contract's default execution with the model's optional `execution` argument
applied. The handler never sees `execution`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from surmap.agent.contracts import ExecutionPolicy, ToolContract, resolve_execution
from surmap.agent.runtime.jobs import JobRunner, ToolHandler, ToolOutcome

__all__ = [
    "BoundTool",
    "ExecutionResolver",
    "PreparedCall",
    "bind_contract_tool",
    "job_tools",
]

ExecutionResolver = Callable[[ToolContract, Mapping[str, object]], ExecutionPolicy]
"""The policy one call runs with, from its contract and the model's arguments."""


@dataclass(frozen=True)
class PreparedCall:
    """One model tool call, ready to run."""

    arguments: Mapping[str, object]
    """The model's arguments without `execution`; what the handler receives."""
    execution: ExecutionPolicy


@dataclass(frozen=True)
class BoundTool:
    """A tool the turn graph binds to the model and dispatches calls to."""

    contract: ToolContract
    handler: ToolHandler
    runner: JobRunner
    resolve: ExecutionResolver

    @property
    def name(self) -> str:
        """The snake_case tool name the model calls."""
        return self.contract.name

    def model_schema(self) -> dict[str, object]:
        """The provider-portable tool definition handed to `bind_tools`.

        `{"type": "function", "function": {"name", "description", "parameters"}}`, with the
        contract's input schema as `parameters`.
        """
        raise NotImplementedError  # TODO(pr-4): implement

    def prepare(self, arguments: Mapping[str, object]) -> PreparedCall:
        """Split the model's arguments into the handler's and the resolved policy.

        Raises `ValueError` when the resolver rejects the `execution` argument.
        """
        raise NotImplementedError  # TODO(pr-4): implement

    async def run(self, call: PreparedCall) -> ToolOutcome:
        """Run the prepared call as a job under its policy."""
        raise NotImplementedError  # TODO(pr-4): implement


def bind_contract_tool(
    contract: ToolContract,
    handler: ToolHandler,
    runner: JobRunner,
    *,
    resolve: ExecutionResolver = resolve_execution,
) -> BoundTool:
    """The tool the model calls as `contract.name`, implemented by `handler`."""
    raise NotImplementedError  # TODO(pr-4): implement


def job_tools(
    runner: JobRunner,
    contracts: Sequence[ToolContract],
    *,
    resolve: ExecutionResolver = resolve_execution,
) -> tuple[BoundTool, ...]:
    """`wait_for_jobs`, `get_job`, `cancel_job` and `list_jobs`, implemented over `runner`.

    `contracts` are the `AgentJobs` tool contracts; each is bound by its name. Raises
    `ValueError` when one of the four is missing.
    """
    raise NotImplementedError  # TODO(pr-4): implement
