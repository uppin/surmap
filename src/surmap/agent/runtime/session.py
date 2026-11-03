"""`AgentSession`: one conversation's turns, steering, cancel and idle job notices.

A turn compiles the turn graph, seeds it with the stored history and appends what each round
adds, so a cancelled turn keeps its completed rounds. `steer` during a turn queues the text as a
pending human message and detaches every blocking tool call; on an idle session it starts a turn.
Notices of jobs that end while no turn runs come out of `idle_events`, for the chat server to
start a `job_event` turn.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from surmap.agent.runtime.events import TurnEvent
from surmap.agent.runtime.graph import TurnCaps
from surmap.agent.runtime.jobs import JobNotice, JobRunner
from surmap.agent.runtime.tools import BoundTool

__all__ = [
    "AgentSession",
    "ConversationStore",
    "InMemoryConversationStore",
    "SteerOutcome",
    "SteerQueued",
    "TurnStarted",
    "TurnTrigger",
]

TurnTrigger = Literal["user", "job_event"]
"""What opened a turn: a person's message, or a job notice that arrived while idle."""


class ConversationStore(Protocol):
    """Where a conversation's history lives between turns."""

    def history(self, conversation_id: str) -> list[BaseMessage]:
        """Every message of the conversation, oldest first; empty for a new one."""
        ...

    def append(self, conversation_id: str, messages: Sequence[BaseMessage]) -> None:
        """Add messages to the end of the conversation."""
        ...


class InMemoryConversationStore:
    """A `ConversationStore` that keeps every conversation in process memory."""

    def history(self, conversation_id: str) -> list[BaseMessage]:
        raise NotImplementedError  # TODO(pr-4): implement

    def append(self, conversation_id: str, messages: Sequence[BaseMessage]) -> None:
        raise NotImplementedError  # TODO(pr-4): implement


@dataclass(frozen=True)
class SteerQueued:
    """A turn was running: the steer is pending and the blocking calls detached."""

    detached: int
    """How many blocking tool calls detached to jobs."""


@dataclass(frozen=True)
class TurnStarted:
    """No turn was running: the steer opened a new one, whose events these are."""

    events: AsyncIterator[TurnEvent]


SteerOutcome = SteerQueued | TurnStarted


class AgentSession:
    """Runs one conversation's turns; at most one turn at a time."""

    def __init__(
        self,
        *,
        conversation_id: str,
        model: BaseChatModel,
        tools: Sequence[BoundTool],
        runner: JobRunner,
        store: ConversationStore,
        caps: TurnCaps | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.model = model
        self.tools = tuple(tools)
        self.runner = runner
        self.store = store
        self.caps = caps if caps is not None else TurnCaps()
        self.system_prompt = system_prompt

    def run_turn(
        self, text: str | None, *, trigger: TurnTrigger = "user"
    ) -> AsyncIterator[TurnEvent]:
        """Run one turn and yield its events; the last is always `TurnFinished`.

        `text` opens the turn — a human message for `"user"`, a system notice for
        `"job_event"`; `None` opens it with the pending messages alone.
        """
        raise NotImplementedError  # TODO(pr-4): implement

    def steer(self, text: str) -> SteerOutcome:
        """Push guidance into the running turn, or start a turn with it when idle."""
        raise NotImplementedError  # TODO(pr-4): implement

    async def cancel(self) -> None:
        """End the running turn and cancel its running jobs; completed rounds stay stored."""
        raise NotImplementedError  # TODO(pr-4): implement

    def idle_events(self) -> AsyncIterator[JobNotice]:
        """Notices of jobs that end while no turn is running."""
        raise NotImplementedError  # TODO(pr-4): implement
