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

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel

from surmap.agent.llm.registry import ModelInfo
from surmap.agent.proto import chat_pb2
from surmap.agent.runtime.graph import TurnCaps
from surmap.agent.runtime.jobs import JobRunner
from surmap.agent.runtime.session import AgentSession
from surmap.agent.runtime.tools import BoundTool

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
        raise NotImplementedError  # TODO(pr-8): implement

    def stream_turn(
        self, conversation_id: str, text: str, *, model_id: str | None = None
    ) -> AsyncIterator[chat_pb2.TurnEvent]:
        """Start a turn with the user's `text` and stream its events, the last `turn_finished`.

        The first event is the `user_message`. Creates the conversation when it is new, on
        `model_id` or the default; a later `model_id` switches the conversation's model.
        Raises `UnknownModelProvider` for a model id no provider builds and `RuntimeError` when
        a turn is already running on the conversation.
        """
        raise NotImplementedError  # TODO(pr-8): implement

    def watch(self, conversation_id: str) -> AsyncIterator[chat_pb2.TurnEvent]:
        """The events of every turn that starts while no `stream_turn` streams it, such as a
        `job_event` turn, until the hub closes or the subscriber goes away."""
        raise NotImplementedError  # TODO(pr-8): implement

    def watchers(self, conversation_id: str) -> int:
        """How many `watch` streams are subscribed to the conversation right now."""
        raise NotImplementedError  # TODO(pr-8): implement

    def steer(self, conversation_id: str, text: str) -> bool:
        """Push guidance into the running turn; False, and nothing started, when none runs."""
        raise NotImplementedError  # TODO(pr-8): implement

    async def cancel(self, conversation_id: str) -> bool:
        """Cancel the running turn and its running jobs; False when no turn runs."""
        raise NotImplementedError  # TODO(pr-8): implement

    def runner(self, conversation_id: str) -> JobRunner | None:
        """The conversation's job runner, for `AgentJobs`; None for an unknown conversation."""
        raise NotImplementedError  # TODO(pr-8): implement

    async def close(self) -> None:
        """Cancel every running turn and job, and end every `watch` stream."""
        raise NotImplementedError  # TODO(pr-8): implement
