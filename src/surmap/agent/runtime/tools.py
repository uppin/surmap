"""Tools the model binds: a `ToolContract` plus its handler, run through the `JobRunner`.

The policy of each call comes from an injected resolver (`surmap.agent.contracts.resolve_execution`
by default): the contract's default execution with the model's optional `execution` argument
applied. The optional `output` argument says whether the result goes to a file
(`surmap.agent.runtime.outputs`). The handler never sees `execution` or `output`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from surmap.agent.contracts import (
    ExecutionPolicy,
    ToolContract,
    resolve_execution,
    resolve_output,
)
from surmap.agent.runtime.jobs import (
    Completed,
    Detached,
    Job,
    JobRunner,
    ToolHandler,
    ToolOutcome,
    WaitMode,
)

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
    """The model's arguments without `execution` and `output`; what the handler receives."""
    execution: ExecutionPolicy
    to_file: bool = False
    """Whether the model asked for the result as a saved file."""


@dataclass(frozen=True)
class BoundTool:
    """A tool the turn graph binds to the model and dispatches calls to."""

    contract: ToolContract
    handler: ToolHandler
    runner: JobRunner
    resolve: ExecutionResolver
    saves_large_results: bool = True
    """Whether a result over the runner's inline limit is saved to a file without being asked;
    off for the file tools, which bound their own results."""

    @property
    def name(self) -> str:
        """The snake_case tool name the model calls."""
        return self.contract.name

    def model_schema(self) -> dict[str, object]:
        """The provider-portable tool definition handed to `bind_tools`.

        `{"type": "function", "function": {"name", "description", "parameters"}}`, with the
        contract's input schema as `parameters`.
        """
        return {
            "type": "function",
            "function": {
                "name": self.contract.name,
                "description": self.contract.description,
                "parameters": dict(self.contract.input_schema),
            },
        }

    def prepare(self, arguments: Mapping[str, object]) -> PreparedCall:
        """Split the model's arguments into the handler's, the resolved policy and `to_file`.

        Raises `ValueError` when the resolver rejects the `execution` argument, or for an
        `output` argument the schema does not allow.
        """
        execution = self.resolve(self.contract, arguments)
        to_file = resolve_output(arguments)
        handed = {name: value for name, value in arguments.items() if name not in _CALL_ARGUMENTS}
        return PreparedCall(arguments=handed, execution=execution, to_file=to_file)

    async def run(self, call: PreparedCall) -> ToolOutcome:
        """Run the prepared call as a job under its policy."""
        return await self.runner.call(
            self.contract,
            call.arguments,
            self.handler,
            policy=call.execution,
            to_file=call.to_file,
            auto_save=self.saves_large_results,
        )

    def content(self, outcome: ToolOutcome, call: PreparedCall) -> str:
        """What the model reads for a call's outcome: a completed result rendered through the
        runner's outputs (inline, or a saved file's reference), else the job handle or error."""
        if isinstance(outcome, Completed):
            return self.runner.outputs.render(
                outcome.job_id,
                self.name,
                outcome.result,
                to_file=call.to_file,
                auto=self.saves_large_results,
            )
        if isinstance(outcome, Detached):
            return (
                f"Job {outcome.job.job_id} ({outcome.job.tool}) is still running: "
                f"{outcome.detail}. Its result will arrive as a notice; use wait_for_jobs, "
                f"get_job or cancel_job with job_id {outcome.job.job_id}."
            )
        return f"Failed: {outcome.error}"


def bind_contract_tool(
    contract: ToolContract,
    handler: ToolHandler,
    runner: JobRunner,
    *,
    resolve: ExecutionResolver = resolve_execution,
    saves_large_results: bool = True,
) -> BoundTool:
    """The tool the model calls as `contract.name`, implemented by `handler`."""
    return BoundTool(
        contract=contract,
        handler=handler,
        runner=runner,
        resolve=resolve,
        saves_large_results=saves_large_results,
    )


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
    handlers: dict[str, ToolHandler] = {
        "wait_for_jobs": lambda arguments: _wait_for_jobs(runner, arguments),
        "get_job": lambda arguments: _get_job(runner, arguments),
        "cancel_job": lambda arguments: _cancel_job(runner, arguments),
        "list_jobs": lambda arguments: _list_jobs(runner, arguments),
    }
    by_name = {contract.name: contract for contract in contracts}
    missing = [name for name in handlers if name not in by_name]
    if missing:
        raise ValueError(f"the AgentJobs contracts lack {', '.join(missing)}")
    return tuple(
        bind_contract_tool(by_name[name], handler, runner, resolve=resolve)
        for name, handler in handlers.items()
    )


_CALL_ARGUMENTS = frozenset({"execution", "output"})
"""The arguments every tool takes that steer the call rather than reach its handler."""

_DEFAULT_WAIT_S = 300


def _job_view(job: Job) -> dict[str, object]:
    return {
        "job_id": job.job_id,
        "tool": job.tool,
        "state": job.state.name,
        "result": job.result,
        "error": job.error,
        "detail": job.detail,
    }


def _job_id(arguments: Mapping[str, object]) -> str:
    job_id = arguments.get("job_id")
    if not isinstance(job_id, str):
        raise ValueError("job_id must be a string")
    return job_id


async def _wait_for_jobs(runner: JobRunner, arguments: Mapping[str, object]) -> dict[str, object]:
    raw_ids = arguments.get("job_ids", [])
    if not isinstance(raw_ids, list) or not all(isinstance(job_id, str) for job_id in raw_ids):
        raise ValueError("job_ids must be a list of job ids")
    mode: WaitMode = "any" if arguments.get("mode") == "ANY" else "all"
    timeout = arguments.get("timeout_s", _DEFAULT_WAIT_S)
    if isinstance(timeout, bool) or not isinstance(timeout, int | float):
        raise ValueError("timeout_s must be a number of seconds")
    waited = await runner.wait(
        [str(job_id) for job_id in raw_ids], mode, timeout * runner.timeout_scale
    )
    return {"timed_out": waited.timed_out, "jobs": [_job_view(job) for job in waited.jobs]}


async def _get_job(runner: JobRunner, arguments: Mapping[str, object]) -> dict[str, object]:
    job_id = _job_id(arguments)
    job = runner.get(job_id)
    if job is None:
        raise ValueError(f"no job {job_id}")
    return _job_view(job)


async def _cancel_job(runner: JobRunner, arguments: Mapping[str, object]) -> dict[str, object]:
    job_id = _job_id(arguments)
    return {"job_id": job_id, "cancelled": runner.cancel(job_id)}


async def _list_jobs(runner: JobRunner, arguments: Mapping[str, object]) -> dict[str, object]:
    return {"jobs": [_job_view(job) for job in runner.jobs()]}
