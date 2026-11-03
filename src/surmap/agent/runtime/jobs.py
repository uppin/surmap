"""Every tool call is a job: `JobRunner` runs it as an asyncio task under an execution policy.

"Sync" only means the caller waits for the job. A SYNC call waits up to its timeout; when the
timeout passes first, `OnTimeout.FAIL` cancels the job and reports a timeout, `OnTimeout.DETACH`
returns a job handle and leaves the job running. An ASYNC call returns a handle at once. Steering
detaches every waiting SYNC call (`detach_blocking`). When a detached or async job ends, a
`JobNotice` is queued on `notices` for the conversation to read.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from surmap.agent.contracts import ExecutionPolicy, ToolContract

__all__ = [
    "Completed",
    "Detached",
    "Failed",
    "Job",
    "JobNotice",
    "JobRunner",
    "JobState",
    "JobWait",
    "ToolHandler",
    "ToolOutcome",
    "WaitMode",
]

ToolHandler = Callable[[Mapping[str, object]], Awaitable[Mapping[str, object]]]
"""A tool's implementation: the model's arguments (without `execution`) to a JSON-able result."""

WaitMode = Literal["all", "any"]
"""Whether `JobRunner.wait` returns when every job has ended or when the first one does."""


class JobState(Enum):
    """Where a job is in its life; mirrors `surmap.agent.v1.JobStatus`."""

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Job:
    """A snapshot of one tool call run by the runner."""

    job_id: str
    """`j-1`, `j-2`, … in the order the runner started them."""
    tool: str
    """The snake_case tool name, e.g. `"run_demo"`."""
    state: JobState
    started_at: float
    """Seconds on the runner's clock when the job started."""
    finished_at: float | None = None
    """Seconds on the runner's clock when the job ended; `None` while it runs."""
    result: Mapping[str, object] | None = None
    """What the handler returned; present once the job has succeeded."""
    error: str | None = None
    """Why the job failed or was cancelled; present once it has."""
    detail: str = ""
    """Human-readable progress, e.g. `"detached by steer"`; empty when there is none."""


@dataclass(frozen=True)
class JobNotice:
    """A detached or async job ended; the conversation reads `text` as a system notice."""

    job: Job
    text: str
    """E.g. `"Job j-3 run_demo succeeded: {...}"`."""


@dataclass(frozen=True)
class Completed:
    """The call returned within its wait; its result goes back to the model inline."""

    job_id: str
    result: Mapping[str, object]


@dataclass(frozen=True)
class Detached:
    """The call keeps running as a job; the model gets the job handle instead of a result."""

    job: Job
    detail: str
    """Why it detached: `"async"`, a DETACH timeout, or the `detach_blocking` reason."""


@dataclass(frozen=True)
class Failed:
    """The call raised, timed out under `OnTimeout.FAIL`, or was cancelled."""

    job_id: str
    error: str


ToolOutcome = Completed | Detached | Failed
"""How one tool call ended for the turn that made it."""


@dataclass(frozen=True)
class JobWait:
    """What `JobRunner.wait` saw: every requested job, in request order."""

    jobs: tuple[Job, ...]
    timed_out: bool
    """Whether the timeout passed before the wait mode was met."""


class JobRunner:
    """Owns every tool call of one conversation as a job."""

    def __init__(
        self,
        *,
        timeout_scale: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """`timeout_scale` is the seconds one policy `timeout_s` unit lasts (tests shrink it)."""
        self.timeout_scale = timeout_scale
        self.clock = clock
        self.notices: asyncio.Queue[JobNotice] = asyncio.Queue()

    async def call(
        self,
        contract: ToolContract,
        arguments: Mapping[str, object],
        handler: ToolHandler,
        *,
        policy: ExecutionPolicy,
    ) -> ToolOutcome:
        """Start `handler(arguments)` as a new job and wait for it as `policy` says."""
        raise NotImplementedError  # TODO(pr-4): implement

    def detach_blocking(self, reason: str) -> int:
        """Detach every SYNC call still waiting, each with `reason` as its detail; how many."""
        raise NotImplementedError  # TODO(pr-4): implement

    async def wait(self, job_ids: Sequence[str], mode: WaitMode, timeout_s: float) -> JobWait:
        """Wait until all (or any) of the jobs have ended, or `timeout_s` seconds pass."""
        raise NotImplementedError  # TODO(pr-4): implement

    def get(self, job_id: str) -> Job | None:
        """The job's current snapshot; `None` for an id this runner never started."""
        raise NotImplementedError  # TODO(pr-4): implement

    def jobs(self) -> tuple[Job, ...]:
        """Every job this runner started, newest first."""
        raise NotImplementedError  # TODO(pr-4): implement

    def cancel(self, job_id: str) -> bool:
        """Cancel a running job; `False` when it has already ended or does not exist."""
        raise NotImplementedError  # TODO(pr-4): implement

    def cancel_all(self) -> int:
        """Cancel every running job; how many were running."""
        raise NotImplementedError  # TODO(pr-4): implement
