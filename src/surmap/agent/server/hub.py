"""`ChatHub`: the server's conversations, one `AgentSession` each, and their event fan-out.

A conversation is created by its first `StreamTurn`. Each has its own `JobRunner`, so its job ids
(`j-1`, `j-2`, …), notices and `AgentJobs` view are its own. Every event a turn yields becomes a
`surmap.agent.v1.TurnEvent` with the conversation's next `seq` (from 1, no gaps) and is recorded,
so `GetConversation` replays exactly what the streams delivered.

`StreamTurn` streams the turn it starts. A job that ends, or a subagent that messages the
conversation, while no turn runs starts a turn of its own; its events go to the conversation's
`WatchConversation` subscribers. With `subagents`, each conversation also binds the subagent tools
(`surmap.agent.subagents`), its subagents running on the conversation's current model. Steering
and cancel act on the running turn only. Without a store, conversations live in memory and
end with the process; with a `PersistentConversationStore` they are restored from it after a
restart (history, model and replay), while jobs and running turns do not survive.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel

from surmap.agent.event_log import TurnLog
from surmap.agent.llm.registry import ModelInfo
from surmap.agent.proto import chat_pb2
from surmap.agent.runtime.events import TurnEvent as RuntimeEvent
from surmap.agent.runtime.graph import TurnCaps
from surmap.agent.runtime.jobs import JobRunner
from surmap.agent.runtime.session import (
    AgentSession,
    InMemoryConversationStore,
    PersistentConversationStore,
    notice_event,
    notice_trigger,
)
from surmap.agent.runtime.tools import BoundTool
from surmap.agent.server.chat_service import turn_event_to_proto
from surmap.agent.subagents import SubagentPool, SubagentSetup, subagent_tools

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
    """The loop that starts a turn for each notice that arrives while idle."""
    log: TurnLog | None = None
    """Logs each turn's start, tool calls and end (`surmap.agent.event_log`)."""

    def __post_init__(self) -> None:
        if self.log is None:
            self.log = TurnLog(self.conversation_id, self.model_id)


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
        subagents: SubagentSetup | None = None,
        store: PersistentConversationStore | None = None,
    ) -> None:
        """`timeout_scale` is each conversation's `JobRunner(timeout_scale=…)`; `subagents`
        binds the subagent tools in every conversation, none without it. With `store`,
        conversations are restored from it after a restart and every event is recorded
        into it; without one they live in memory and end with the process."""
        self.model_factory = model_factory
        self.tools = tools
        self.list_models = models
        self.default_model_id = default_model_id
        self.system_prompt = system_prompt
        self.caps = caps
        self.timeout_scale = timeout_scale
        self.subagents = subagents
        self._store = store
        self._conversations: dict[str, Conversation] = {}

    def get(self, conversation_id: str) -> Conversation | None:
        """The conversation `conversation_id`, restored from the store when this hub has
        not opened it yet; None when no turn has ever started it."""
        conversation = self._conversations.get(conversation_id)
        if conversation is None and self._store is not None:
            conversation = self._restore(conversation_id)
        return conversation

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
        conversation = self.get(conversation_id)
        if conversation is not None and _turn_running(conversation.session):
            raise RuntimeError(f"a turn is already running in {conversation_id}")
        if conversation is None:
            conversation = self._open(conversation_id, model_id or self.default_model_id)
        elif model_id is not None and model_id != conversation.model_id:
            conversation.session.model = self.model_factory(model_id)
            conversation.model_id = model_id
            if self._store is not None:
                self._store.remember_model(conversation_id, model_id)
        turn_id = uuid.uuid4().hex
        # Starting the turn before the first yield makes it running at once, so no other
        # StreamTurn can pass the busy check while this one is suspended.
        events = conversation.session.run_turn(text)
        try:
            yield _record_user_message(conversation, turn_id, text, self._store)
            async for event in events:
                yield _record(conversation, turn_id, event, self._store)
        finally:
            if _turn_running(conversation.session):
                # The client went away mid-turn: end it, as a closed stream always has.
                await conversation.session.cancel()

    def watch(self, conversation_id: str) -> AsyncIterator[chat_pb2.TurnEvent]:
        """The events of every turn that starts while no `stream_turn` streams it, such as a
        `job_event` turn, until the hub closes or the subscriber goes away."""
        conversation = self.get(conversation_id)
        if conversation is None:
            raise KeyError(conversation_id)
        return self._watch(conversation)

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
        conversation = self.get(conversation_id)
        return None if conversation is None else conversation.session.runner

    async def close(self) -> None:
        """Cancel every running turn and job, end every `watch` stream, and close the store."""
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
        if self._store is not None:
            self._store.close()

    def _restore(self, conversation_id: str) -> Conversation | None:
        """The conversation as the store kept it — model, replay events, and a session whose
        history the store still holds — or None when the store has never seen it."""
        assert self._store is not None
        model_id = self._store.model_id(conversation_id)
        payloads = self._store.events(conversation_id)
        if model_id is None and not payloads:
            return None
        events: list[chat_pb2.TurnEvent] = []
        for payload in payloads:
            event = chat_pb2.TurnEvent()
            event.ParseFromString(payload)
            events.append(event)
        return self._build(conversation_id, model_id or self.default_model_id, events)

    def _open(self, conversation_id: str, model_id: str) -> Conversation:
        """A new conversation on `model_id`, with its own runner, session and idle loop."""
        if self._store is not None:
            self._store.remember_model(conversation_id, model_id)
        return self._build(conversation_id, model_id, [])

    def _build(
        self, conversation_id: str, model_id: str, events: list[chat_pb2.TurnEvent]
    ) -> Conversation:
        """A conversation on `model_id` with `events` as its replay, registered on this hub."""
        runner = JobRunner(timeout_scale=self.timeout_scale)
        model = self.model_factory(model_id)
        tools = list(self.tools(runner))
        if self.subagents is not None:
            pool = SubagentPool(
                conversation_id=conversation_id,
                runner=runner,
                model=lambda: session.model,
                tools=self.tools,
                setup=self.subagents,
                caps=self.caps,
            )
            tools.extend(subagent_tools(pool))
        session = AgentSession(
            conversation_id=conversation_id,
            model=model,
            tools=tools,
            runner=runner,
            store=self._store if self._store is not None else InMemoryConversationStore(),
            caps=self.caps,
            system_prompt=self.system_prompt,
        )
        conversation = Conversation(
            conversation_id=conversation_id, model_id=model_id, session=session, events=events
        )
        conversation.idle = asyncio.ensure_future(self._job_turns(conversation))
        self._conversations[conversation_id] = conversation
        return conversation

    async def _job_turns(self, conversation: Conversation) -> None:
        """Start a turn for each notice that arrives while the conversation is idle."""
        async for notice in conversation.session.idle_events():
            turn_id = uuid.uuid4().hex
            opening = _record(conversation, turn_id, notice_event(notice), self._store)
            _publish(conversation, opening)
            trigger = notice_trigger(notice)
            async for event in conversation.session.run_turn(notice.text, trigger=trigger):
                _publish(conversation, _record(conversation, turn_id, event, self._store))

    async def _watch(self, conversation: Conversation) -> AsyncIterator[chat_pb2.TurnEvent]:
        queue: asyncio.Queue[chat_pb2.TurnEvent | None] = asyncio.Queue()
        conversation.watchers.append(queue)
        try:
            while (event := await queue.get()) is not None:
                yield event
        finally:
            conversation.watchers.remove(queue)


def _turn_running(session: AgentSession) -> bool:
    """Whether a turn is running on `session`."""
    return session.running


def _record(
    conversation: Conversation,
    turn_id: str,
    event: RuntimeEvent,
    store: PersistentConversationStore | None = None,
) -> chat_pb2.TurnEvent:
    """The runtime event as the conversation's next `TurnEvent`, kept for replay (and
    recorded into `store`, when the hub has one, so the replay survives a restart)."""
    if conversation.log is not None:
        conversation.log.observe(turn_id, event)
    proto = turn_event_to_proto(
        event,
        conversation_id=conversation.conversation_id,
        turn_id=turn_id,
        seq=len(conversation.events) + 1,
    )
    conversation.events.append(proto)
    if store is not None:
        store.record_event(conversation.conversation_id, proto.SerializeToString())
    return proto


def _record_user_message(
    conversation: Conversation,
    turn_id: str,
    text: str,
    store: PersistentConversationStore | None = None,
) -> chat_pb2.TurnEvent:
    """The user's message as the conversation's next `TurnEvent`, kept for replay (and
    recorded into `store`, when the hub has one, so the replay survives a restart)."""
    if conversation.log is not None:
        conversation.log.user_message(turn_id)
    proto = chat_pb2.TurnEvent(
        conversation_id=conversation.conversation_id,
        turn_id=turn_id,
        seq=len(conversation.events) + 1,
        user_message=chat_pb2.UserMessage(text=text),
    )
    conversation.events.append(proto)
    if store is not None:
        store.record_event(conversation.conversation_id, proto.SerializeToString())
    return proto


def _publish(conversation: Conversation, event: chat_pb2.TurnEvent) -> None:
    """Hand a job-event turn's event to every `WatchConversation` subscriber."""
    for queue in conversation.watchers:
        queue.put_nowait(event)
