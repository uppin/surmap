"""What a turn yields, in order; the chat server maps each onto `surmap.agent.v1.TurnEvent`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from surmap.agent.contracts import ExecutionPolicy
from surmap.agent.runtime.jobs import Job, JobState, ToolOutcome

__all__ = [
    "FinishReason",
    "JobUpdate",
    "SteerApplied",
    "SubagentMessage",
    "SubagentStatus",
    "TextDelta",
    "ToolCallFinished",
    "ToolCallStarted",
    "TurnError",
    "TurnEvent",
    "TurnFinished",
]

FinishReason = Literal["stop", "round_cap", "repeated_failure", "cancelled", "error"]
"""Why a turn ended: the model answered, a cap routed it to `cut_off`, it was cancelled, or an
error (a `TurnError` precedes it) ended it."""


@dataclass(frozen=True)
class TextDelta:
    """The next piece of the model's answer text."""

    text: str


@dataclass(frozen=True)
class ToolCallStarted:
    """The model asked for a tool call and the runner started it."""

    call_id: str
    """The model's tool-call id."""
    tool: str
    arguments: Mapping[str, object]
    """The model's arguments without the `execution` override."""
    execution: ExecutionPolicy
    """The policy the call runs with: the contract default merged with the override."""


@dataclass(frozen=True)
class ToolCallFinished:
    """A tool call ended for this turn: a result, a failure, or a detach to a job."""

    call_id: str
    tool: str
    outcome: ToolOutcome


@dataclass(frozen=True)
class JobUpdate:
    """A detached or async job changed state while the turn ran."""

    job: Job


@dataclass(frozen=True)
class SteerApplied:
    """Steering guidance joined the turn; the model reads it on its next call."""

    text: str
    detached_call_ids: tuple[str, ...]
    """The tool calls that detached to jobs so the model could act on the guidance."""


@dataclass(frozen=True)
class SubagentMessage:
    """A subagent's message reached the conversation; the model reads it as a notice."""

    subagent_id: str
    name: str
    text: str
    """What the subagent wrote."""


@dataclass(frozen=True)
class SubagentStatus:
    """Where a subagent is in its task, for the person's tasks panel; no model reads it.

    It belongs to no turn: the chat hub hands it to the conversation's watchers as it happens.
    """

    subagent_id: str
    name: str
    job_id: str
    """The job its latest turn runs as."""
    state: JobState
    """Where its latest turn is."""
    detail: str
    """What it last reported doing with `report_status`; empty until it reports."""


@dataclass(frozen=True)
class TurnFinished:
    """The turn ended; always the last event."""

    reason: FinishReason


@dataclass(frozen=True)
class TurnError:
    """Something other than a tool failure went wrong; a `TurnFinished("error")` follows."""

    message: str


TurnEvent = (
    TextDelta
    | ToolCallStarted
    | ToolCallFinished
    | JobUpdate
    | SteerApplied
    | SubagentMessage
    | SubagentStatus
    | TurnFinished
    | TurnError
)
"""One thing that happened in a turn."""
