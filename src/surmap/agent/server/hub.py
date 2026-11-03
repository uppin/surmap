"""`ChatHub`: the server's conversations, one `AgentSession` each, and their event fan-out.

A conversation is created by its first `StreamTurn`. Each has its own `JobRunner`, so its job ids
(`j-1`, `j-2`, …), notices and `AgentJobs` view are its own. Every event a turn yields becomes a
`surmap.agent.v1.TurnEvent` with the conversation's next `seq` (from 1, no gaps) and is recorded,
so `GetConversation` replays exactly what the streams delivered.

`StreamTurn` streams the turn it starts. A job that ends while no turn runs starts a `job_event`
turn of its own; its events go to the conversation's `WatchConversation` subscribers. Steering
and cancel act on the running turn only. Conversations live in memory and end with the process.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel

from surmap.agent.llm.registry import ModelInfo
from surmap.agent.proto import chat_pb2
from surmap.agent.runtime.events import JobUpdate
from surmap.agent.runtime.events import TurnEvent as RuntimeEvent
from surmap.agent.runtime.graph import TurnCaps
from surmap.agent.runtime.jobs import JobRunner
from surmap.agent.runtime.session import AgentSession, InMemoryConversationStore
from surmap.agent.runtime.tools import BoundTool
from surmap.agent.server.chat_service import turn_event_to_proto

__all__ = ["ChatHub", "Conversation", "ModelFactory", "ModelLister", "ToolFactory"]

ModelFactory = Callable[[str], BaseChatModel]
"""The chat model a model id names; raises `UnknownModelProvider` for a provider it lacks."""

ToolFactory = Callable[[JobRunner], Sequence[BoundTool]]
"""The tools one conversation binds, over that conversation's own runner."""

ModelLister = Callable[[], Sequence[ModelInfo]]
"""The chat models reachable right now, as `ChatModelRegistry.available` lists them."""


@dataclass
class Conversation:
    """One conversation: its session, the model it runs on, and every event so far."""

    conversation_id: str
    model_id: str
    session: AgentSession
    events: list[chat_pb2.TurnEvent] = field(default_factory=list)
    """Every event so far, in `seq` order; what `GetConversation` replays."""
    watchers: list[asyncio.Queue[chat_pb2.TurnEvent | None]] = field(default_factory=list)
    """The `WatchConversation` streams subscribed; `None` is queued when the hub closes."""
    idle: asyncio.Task[None] | None = None
    """The loop that starts a `job_event` turn for each job that ends while idle."""


class ChatHub:
    """The server's conversations and the streams subscribed to them."""

    def __init__(
        self,
        *,
        model_factory: ModelFactory,
        tools: ToolFactory,
        models: ModelLister,
        default_model_id: str,
        system_prompt: str | None = None,
        caps: TurnCaps | None = None,
        timeout_scale: float = 1.0,
    ) -> None:
        """`timeout_scale` is each conversation's `JobRunner(timeout_scale=…)`."""
        self.model_factory = model_factory
        self.tools = tools
        self.list_models = models
        self.default_model_id = default_model_id
        self.system_prompt = system_prompt
        self.caps = caps
        self.timeout_scale = timeout_scale
        self._conversations: dict[str, Conversation] = {}

    def get(self, conversation_id: str) -> Conversation | None:
        """The conversation `conversation_id`, or None when no turn has started it."""
        return self._conversations.get(conversation_id)

    def busy(self, conversation_id: str) -> bool:
        """Whether a turn is running on the conversation right now."""
        conversation = self._conversations.get(conversation_id)
        return conversation is not None and _turn_running(conversation.session)

    async def stream_turn(
        self, conversation_id: str, text: str, *, model_id: str | None = None
    ) -> AsyncIterator[chat_pb2.TurnEvent]:
        """Start a turn with the user's `text` and stream its events, the last `turn_finished`.

        The first event is the `user_message`. Creates the conversation when it is new, on
        `model_id` or the default; a later `model_id` switches the conversation's model.
        Raises `UnknownModelProvider` for a model id no provider builds and `RuntimeError` when
        a turn is already running on the conversation.
        """
        conversation = self._conversations.get(conversation_id)
        if conversation is not None and _turn_running(conversation.session):
            raise RuntimeError(f"a turn is already running in {conversation_id}")
        if conversation is None:
            conversation = self._open(conversation_id, model_id or self.default_model_id)
        elif model_id is not None and model_id != conversation.model_id:
            conversation.session.model = self.model_factory(model_id)
            conversation.model_id = model_id
        turn_id = uuid.uuid4().hex
        # Starting the turn before the first yield makes it running at once, so no other
        # StreamTurn can pass the busy check while this one is suspended.
        events = conversation.session.run_turn(text)
        try:
            yield _record_user_message(conversation, turn_id, text)
            async for event in events:
                yield _record(conversation, turn_id, event)
        finally:
            if _turn_running(conversation.session):
                # The client went away mid-turn: end it, as a closed stream always has.
                await conversation.session.cancel()

    def watch(self, conversation_id: str) -> AsyncIterator[chat_pb2.TurnEvent]:
        """The events of every turn that starts while no `stream_turn` streams it, such as a
        `job_event` turn, until the hub closes or the subscriber goes away."""
        return self._watch(self._conversations[conversation_id])

    def watchers(self, conversation_id: str) -> int:
        """How many `watch` streams are subscribed to the conversation right now."""
        conversation = self._conversations.get(conversation_id)
        return 0 if conversation is None else len(conversation.watchers)

    def steer(self, conversation_id: str, text: str) -> bool:
        """Push guidance into the running turn; False, and nothing started, when none runs."""
        conversation = self._conversations.get(conversation_id)
        if conversation is None or not _turn_running(conversation.session):
            return False
        conversation.session.steer(text)
        return True

    async def cancel(self, conversation_id: str) -> bool:
        """Cancel the running turn and its running jobs; False when no turn runs."""
        conversation = self._conversations.get(conversation_id)
        if conversation is None or not _turn_running(conversation.session):
            return False
        await conversation.session.cancel()
        return True

    def runner(self, conversation_id: str) -> JobRunner | None:
        """The conversation's job runner, for `AgentJobs`; None for an unknown conversation."""
        conversation = self._conversations.get(conversation_id)
        return None if conversation is None else conversation.session.runner

    async def close(self) -> None:
        """Cancel every running turn and job, and end every `watch` stream."""
        conversations = list(self._conversations.values())
        idle = [c.idle for c in conversations if c.idle is not None]
        for conversation in conversations:
            if conversation.idle is not None:
                conversation.idle.cancel()
        for conversation in conversations:
            if _turn_running(conversation.session):
                await conversation.session.cancel()
            conversation.session.runner.cancel_all()
            for queue in conversation.watchers:
                queue.put_nowait(None)
        await asyncio.gather(*idle, return_exceptions=True)

    def _open(self, conversation_id: str, model_id: str) -> Conversation:
        """A new conversation on `model_id`, with its own runner, session and idle loop."""
        runner = JobRunner(timeout_scale=self.timeout_scale)
        session = AgentSession(
            conversation_id=conversation_id,
            model=self.model_factory(model_id),
            tools=self.tools(runner),
            runner=runner,
            store=InMemoryConversationStore(),
            caps=self.caps,
            system_prompt=self.system_prompt,
        )
        conversation = Conversation(
            conversation_id=conversation_id, model_id=model_id, session=session
        )
        conversation.idle = asyncio.ensure_future(self._job_turns(conversation))
        self._conversations[conversation_id] = conversation
        return conversation

    async def _job_turns(self, conversation: Conversation) -> None:
        """Start a `job_event` turn for each job that ends while the conversation is idle."""
        async for notice in conversation.session.idle_events():
            turn_id = uuid.uuid4().hex
            opening = _record(conversation, turn_id, JobUpdate(job=notice.job))
            _publish(conversation, opening)
            async for event in conversation.session.run_turn(notice.text, trigger="job_event"):
                _publish(conversation, _record(conversation, turn_id, event))

    async def _watch(self, conversation: Conversation) -> AsyncIterator[chat_pb2.TurnEvent]:
        queue: asyncio.Queue[chat_pb2.TurnEvent | None] = asyncio.Queue()
        conversation.watchers.append(queue)
        try:
            while (event := await queue.get()) is not None:
                yield event
        finally:
            conversation.watchers.remove(queue)


def _turn_running(session: AgentSession) -> bool:
    """Whether a turn is running on `session`.

    `AgentSession` has no public probe for this, so the hub reads the `_active` flag the session
    sets when a turn starts and clears when it ends: the same state its own `run_turn` checks.
    """
    return session._active


def _record(conversation: Conversation, turn_id: str, event: RuntimeEvent) -> chat_pb2.TurnEvent:
    """The runtime event as the conversation's next `TurnEvent`, kept for replay."""
    proto = turn_event_to_proto(
        event,
        conversation_id=conversation.conversation_id,
        turn_id=turn_id,
        seq=len(conversation.events) + 1,
    )
    conversation.events.append(proto)
    return proto


def _record_user_message(conversation: Conversation, turn_id: str, text: str) -> chat_pb2.TurnEvent:
    """The user's message as the conversation's next `TurnEvent`, kept for replay."""
    proto = chat_pb2.TurnEvent(
        conversation_id=conversation.conversation_id,
        turn_id=turn_id,
        seq=len(conversation.events) + 1,
        user_message=chat_pb2.UserMessage(text=text),
    )
    conversation.events.append(proto)
    return proto


def _publish(conversation: Conversation, event: chat_pb2.TurnEvent) -> None:
    """Hand a job-event turn's event to every `WatchConversation` subscriber."""
    for queue in conversation.watchers:
        queue.put_nowait(event)
