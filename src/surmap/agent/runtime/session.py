"""`AgentSession`: one conversation's turns, steering, cancel and idle job notices.

A turn compiles the turn graph, seeds it with the stored history and appends what each round
adds, so a cancelled turn keeps its completed rounds. `steer` during a turn queues the text as a
pending human message and detaches every blocking tool call; on an idle session it starts a turn.
Notices — jobs that end, messages from subagents — that arrive while no turn runs come out of
`idle_events`, for the chat server to start a turn with (`notice_event` is its opening event).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from surmap.agent.runtime.events import (
    FinishReason,
    JobUpdate,
    SubagentMessage,
    TurnError,
    TurnEvent,
    TurnFinished,
)
from surmap.agent.runtime.graph import (
    KIND_KEY,
    NOTICE_KIND,
    STEER_DETACH_REASON,
    STEER_KIND,
    SUBAGENT_KIND,
    TurnCaps,
    build_turn_graph,
    turn_input,
)
from surmap.agent.runtime.jobs import JobNotice, JobRunner, JobState, Notice, SubagentNotice
from surmap.agent.runtime.tools import BoundTool

__all__ = [
    "AgentSession",
    "ConversationStore",
    "InMemoryConversationStore",
    "SteerOutcome",
    "SteerQueued",
    "TurnStarted",
    "TurnTrigger",
    "notice_event",
    "notice_trigger",
]

TurnTrigger = Literal["user", "job_event", "subagent_message"]
"""What opened a turn: a person's message, or a job's or a subagent's notice that arrived while
idle."""

_TRIGGER_KINDS: dict[TurnTrigger, str] = {
    "job_event": NOTICE_KIND,
    "subagent_message": SUBAGENT_KIND,
}


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

    def __init__(self) -> None:
        self._conversations: dict[str, list[BaseMessage]] = {}

    def history(self, conversation_id: str) -> list[BaseMessage]:
        return list(self._conversations.get(conversation_id, []))

    def append(self, conversation_id: str, messages: Sequence[BaseMessage]) -> None:
        self._conversations.setdefault(conversation_id, []).extend(messages)


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
        self._pending: list[BaseMessage] = []
        self._notice_events: dict[str, TurnEvent] = {}
        """The event each drained notice's message reports once it is in the history."""
        self._active = False
        self._task: asyncio.Task[FinishReason] | None = None

    @property
    def running(self) -> bool:
        """Whether a turn is running on this session right now."""
        return self._active

    def run_turn(
        self, text: str | None, *, trigger: TurnTrigger = "user"
    ) -> AsyncIterator[TurnEvent]:
        """Run one turn and yield its events; the last is always `TurnFinished`.

        `text` opens the turn — a human message for `"user"`, a notice tagged with its kind for
        `"job_event"` and `"subagent_message"`; `None` opens it with the pending messages alone.
        """
        if self._active:
            raise RuntimeError("a turn is already running on this conversation")
        opening = None
        if text is not None:
            kind = _TRIGGER_KINDS.get(trigger)
            kwargs = {KIND_KEY: kind} if kind is not None else {}
            opening = HumanMessage(content=text, id=uuid.uuid4().hex, additional_kwargs=kwargs)
        events: asyncio.Queue[TurnEvent] = asyncio.Queue()
        self._active = True
        task = asyncio.ensure_future(self._drive(opening, events))
        self._task = task
        task.add_done_callback(lambda ended: self._ended(ended, events))
        return self._stream(task, events)

    def steer(self, text: str) -> SteerOutcome:
        """Push guidance into the running turn, or start a turn with it when idle."""
        if not self._active:
            return TurnStarted(events=self.run_turn(text))
        self._pending.append(
            HumanMessage(
                content=text, id=uuid.uuid4().hex, additional_kwargs={KIND_KEY: STEER_KIND}
            )
        )
        return SteerQueued(detached=self.runner.detach_blocking(STEER_DETACH_REASON))

    async def cancel(self) -> None:
        """End the running turn and cancel its running jobs; completed rounds stay stored."""
        running = [job.job_id for job in self.runner.jobs() if job.state is JobState.RUNNING]
        self.runner.cancel_all()
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.wait({task})
        if running:
            await self.runner.wait(running, "all", timeout_s=1.0)

    async def idle_events(self) -> AsyncIterator[Notice]:
        """Notices — of jobs that end, of subagents' messages — that arrive while no turn runs."""
        while True:
            notice = await self.runner.notices.get()
            if self._active:
                self._pending.append(self._notice_message(notice))
            else:
                yield notice

    async def _stream(
        self, task: asyncio.Task[FinishReason], events: asyncio.Queue[TurnEvent]
    ) -> AsyncIterator[TurnEvent]:
        try:
            while True:
                event = await events.get()
                yield event
                if isinstance(event, TurnFinished):
                    return
        finally:
            if not task.done():
                task.cancel()

    async def _drive(
        self, opening: HumanMessage | None, events: asyncio.Queue[TurnEvent]
    ) -> FinishReason:
        if opening is not None:
            self.store.append(self.conversation_id, [opening])
        while True:
            reason = await self._run_graph(events)
            if reason != "stop" or not self._pending:
                self._active = False
                return reason

    async def _run_graph(self, events: asyncio.Queue[TurnEvent]) -> FinishReason:
        history = self.store.history(self.conversation_id)
        if self.system_prompt is not None:
            history = [SystemMessage(content=self.system_prompt), *history]
        graph = build_turn_graph(self.model, self.tools, self._drain, self.caps)
        reason: FinishReason = "stop"
        async for mode, payload in graph.astream(
            turn_input(history), stream_mode=["custom", "updates"]
        ):
            if mode == "custom":
                events.put_nowait(cast(TurnEvent, payload))
                continue
            if not isinstance(payload, dict):
                continue
            for update in payload.values():
                if not isinstance(update, dict):
                    continue
                new: list[BaseMessage] = update.get("messages") or []
                self.store.append(self.conversation_id, new)
                for message in new:
                    reported = self._notice_events.pop(message.id or "", None)
                    if reported is not None:
                        events.put_nowait(reported)
                if update.get("finish_reason"):
                    reason = update["finish_reason"]
        return reason

    def _drain(self) -> list[BaseMessage]:
        """The notices and then the steers queued since the last model call."""
        drained: list[BaseMessage] = []
        while not self.runner.notices.empty():
            drained.append(self._notice_message(self.runner.notices.get_nowait()))
        steers = [m for m in self._pending if m.additional_kwargs.get(KIND_KEY) == STEER_KIND]
        drained.extend(m for m in self._pending if m not in steers)
        drained.extend(steers)
        self._pending.clear()
        return drained

    def _notice_message(self, notice: Notice) -> HumanMessage:
        kind = _TRIGGER_KINDS[notice_trigger(notice)]
        message = HumanMessage(
            content=notice.text, id=uuid.uuid4().hex, additional_kwargs={KIND_KEY: kind}
        )
        self._notice_events[str(message.id)] = notice_event(notice)
        return message

    def _ended(self, task: asyncio.Task[FinishReason], events: asyncio.Queue[TurnEvent]) -> None:
        """However the turn's task ended, keep the history valid and close the event stream."""
        self._active = False
        if task.cancelled():
            reason: FinishReason = "cancelled"
        elif (error := task.exception()) is not None:
            events.put_nowait(TurnError(message=str(error) or type(error).__name__))
            reason = "error"
        else:
            reason = task.result()
        self._close_dangling_calls()
        events.put_nowait(TurnFinished(reason=reason))

    def _close_dangling_calls(self) -> None:
        """Answer tool calls a stopped turn never ran, so the history stays valid."""
        history = self.store.history(self.conversation_id)
        answered = {m.tool_call_id for m in history if isinstance(m, ToolMessage)}
        unanswered = [
            call
            for message in history
            if isinstance(message, AIMessage)
            for call in message.tool_calls
            if call["id"] not in answered
        ]
        self.store.append(
            self.conversation_id,
            [
                ToolMessage(
                    content="Not run: the turn ended before this call finished.",
                    tool_call_id=str(call["id"]),
                    name=call["name"],
                    status="error",
                )
                for call in unanswered
            ],
        )


def notice_trigger(notice: Notice) -> TurnTrigger:
    """The trigger of the turn `notice` opens while the session idles."""
    return "subagent_message" if isinstance(notice, SubagentNotice) else "job_event"


def notice_event(notice: Notice) -> TurnEvent:
    """What the turn reports for `notice`: the job's update, or the subagent's message."""
    if isinstance(notice, JobNotice):
        return JobUpdate(job=notice.job)
    return SubagentMessage(subagent_id=notice.subagent_id, name=notice.name, text=notice.message)
