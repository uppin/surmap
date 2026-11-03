"""Every tool call is a job: `JobRunner` runs it as an asyncio task under an execution policy.

"Sync" only means the caller waits for the job. A SYNC call waits up to its timeout; when the
timeout passes first, `OnTimeout.FAIL` cancels the job and reports a timeout, `OnTimeout.DETACH`
returns a job handle and leaves the job running. An ASYNC call returns a handle at once. Steering
detaches every waiting SYNC call (`detach_blocking`); a SYNC call whose caller is cancelled while
it waits is cancelled with it. When a detached or async job ends, a `JobNotice` is queued on
`notices` for the conversation to read.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from surmap.agent.contracts import ExecutionMode, ExecutionPolicy, OnTimeout, ToolContract

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


class _Entry:
    """The runner's mutable record of one job; `Job` is its frozen snapshot."""

    def __init__(self, job_id: str, tool: str, started_at: float) -> None:
        self.job_id = job_id
        self.tool = tool
        self.started_at = started_at
        self.state = JobState.RUNNING
        self.finished_at: float | None = None
        self.result: Mapping[str, object] | None = None
        self.error: str | None = None
        self.detail = ""
        self.blocking = False
        """Whether a SYNC caller is waiting on this job right now."""
        self.detached = False
        """Whether the job outlives its call, so its end is reported as a notice."""
        self.done = asyncio.Event()
        self.detach = asyncio.Event()
        self.task: asyncio.Task[Mapping[str, object]] | None = None

    def snapshot(self) -> Job:
        return Job(
            job_id=self.job_id,
            tool=self.tool,
            state=self.state,
            started_at=self.started_at,
            finished_at=self.finished_at,
            result=self.result,
            error=self.error,
            detail=self.detail,
        )


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
        self._entries: dict[str, _Entry] = {}

    async def call(
        self,
        contract: ToolContract,
        arguments: Mapping[str, object],
        handler: ToolHandler,
        *,
        policy: ExecutionPolicy,
    ) -> ToolOutcome:
        """Start `handler(arguments)` as a new job and wait for it as `policy` says."""
        entry = _Entry(f"j-{len(self._entries) + 1}", contract.name, self.clock())
        self._entries[entry.job_id] = entry
        task = asyncio.ensure_future(handler(arguments))
        entry.task = task
        task.add_done_callback(lambda finished: self._finish(entry, finished))
        if policy.mode is ExecutionMode.ASYNC:
            return self._detach(entry, "async")
        timeout = policy.timeout_s * self.timeout_scale
        entry.blocking = True
        waiting = {
            asyncio.ensure_future(entry.done.wait()),
            asyncio.ensure_future(entry.detach.wait()),
        }
        try:
            await asyncio.wait(waiting, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            # The caller went away mid-wait: nobody will read this result and, never detached,
            # it would end unreported — so the job ends with its caller.
            task.cancel()
            raise
        finally:
            entry.blocking = False
            for pending in waiting:
                pending.cancel()
        if entry.done.is_set():
            return self._outcome(entry)
        if entry.detach.is_set():
            return Detached(job=entry.snapshot(), detail=entry.detail)
        if policy.on_timeout is OnTimeout.DETACH:
            return self._detach(entry, f"detached after the {policy.timeout_s}s timeout")
        entry.state = JobState.FAILED
        entry.error = f"timed out after {policy.timeout_s}s"
        task.cancel()
        await asyncio.wait({task})
        await entry.done.wait()
        return Failed(job_id=entry.job_id, error=entry.error)

    def detach_blocking(self, reason: str) -> int:
        """Detach every SYNC call still waiting, each with `reason` as its detail; how many."""
        waiting = [entry for entry in self._entries.values() if entry.blocking]
        for entry in waiting:
            self._detach(entry, reason)
        return len(waiting)

    async def wait(self, job_ids: Sequence[str], mode: WaitMode, timeout_s: float) -> JobWait:
        """Wait until all (or any) of the jobs have ended, or `timeout_s` seconds pass."""
        entries = [self._entry(job_id) for job_id in job_ids]
        waiting = {asyncio.ensure_future(entry.done.wait()) for entry in entries}
        try:
            if waiting:
                await asyncio.wait(
                    waiting,
                    timeout=timeout_s,
                    return_when=(
                        asyncio.ALL_COMPLETED if mode == "all" else asyncio.FIRST_COMPLETED
                    ),
                )
        finally:
            for pending in waiting:
                pending.cancel()
        ended = [entry.done.is_set() for entry in entries]
        met = all(ended) if mode == "all" else (any(ended) or not entries)
        return JobWait(jobs=tuple(entry.snapshot() for entry in entries), timed_out=not met)

    def get(self, job_id: str) -> Job | None:
        """The job's current snapshot; `None` for an id this runner never started."""
        entry = self._entries.get(job_id)
        return entry.snapshot() if entry is not None else None

    def jobs(self) -> tuple[Job, ...]:
        """Every job this runner started, newest first."""
        return tuple(entry.snapshot() for entry in reversed(self._entries.values()))

    def cancel(self, job_id: str) -> bool:
        """Cancel a running job; `False` when it has already ended or does not exist."""
        entry = self._entries.get(job_id)
        if entry is None or entry.task is None or entry.done.is_set():
            return False
        return entry.task.cancel()

    def cancel_all(self) -> int:
        """Cancel every running job; how many were running."""
        return sum(self.cancel(job_id) for job_id in list(self._entries))

    def _entry(self, job_id: str) -> _Entry:
        entry = self._entries.get(job_id)
        if entry is None:
            raise ValueError(f"no job {job_id}")
        return entry

    def _detach(self, entry: _Entry, detail: str) -> Detached:
        entry.detached = True
        entry.detail = detail
        entry.detach.set()
        return Detached(job=entry.snapshot(), detail=detail)

    @staticmethod
    def _outcome(entry: _Entry) -> ToolOutcome:
        if entry.state is JobState.SUCCEEDED and entry.result is not None:
            return Completed(job_id=entry.job_id, result=entry.result)
        return Failed(job_id=entry.job_id, error=entry.error or "the job did not succeed")

    def _finish(self, entry: _Entry, task: asyncio.Task[Mapping[str, object]]) -> None:
        """Record how the handler ended; runs when its task is done, however it ended."""
        if entry.state is JobState.RUNNING:
            if task.cancelled():
                entry.state = JobState.CANCELLED
                entry.error = "cancelled"
            elif (error := task.exception()) is not None:
                entry.state = JobState.FAILED
                entry.error = str(error) or type(error).__name__
            else:
                entry.state = JobState.SUCCEEDED
                entry.result = task.result()
        entry.finished_at = self.clock()
        entry.done.set()
        if entry.detached and entry.state is not JobState.CANCELLED:
            job = entry.snapshot()
            self.notices.put_nowait(JobNotice(job=job, text=_notice_text(job)))


def _notice_text(job: Job) -> str:
    head = f"Job {job.job_id} {job.tool} {job.state.name.lower()}"
    if job.state is JobState.SUCCEEDED:
        return f"{head}: {json.dumps(job.result, default=str)}"
    return f"{head}: {job.error}"
