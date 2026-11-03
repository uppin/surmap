"""Builders and drivers for the agent chat server tests.

`a_chat_rig` is a real `ChatHub` mounted in memory as `ChatService` + `AgentJobs`, answering
with n4's `ScriptedChatModel` and calling n4's `FakeToolHandler`s bound to the real `SurveyTools`
contracts, so the SurMap tools themselves (n7) stay out of the chat-service tests. `TurnStream`
reads a server stream in the background so a test can steer or cancel while it runs. Nothing
here sleeps: waits are on events, bounded by `STEP_TIMEOUT_S`.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass

from google.protobuf.message import Message
from langchain_core.language_models import BaseChatModel
from PIL import Image

from surmap.agent.contracts import ToolContract, tool_contracts
from surmap.agent.llm.registry import ModelInfo, UnknownModelProvider
from surmap.agent.proto import chat_pb2, jobs_pb2, map_tools_pb2, survey_tools_pb2
from surmap.agent.runtime.jobs import JobRunner
from surmap.agent.runtime.tools import BoundTool, bind_contract_tool, job_tools
from surmap.agent.server.chat_service import agent_jobs_handlers, chat_handlers
from surmap.agent.server.hub import ChatHub
from surmap.agent.services import agent_jobs_module, chat_service_module
from surmap.agent.tools.port import GalleryEntry
from surmap.agent.tools.workspace import (
    FrameDetections,
    FrameImage,
    FrameRecord,
    ObjectBox,
    RunInfo,
    SceneInfo,
    StoredObject,
)
from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.in_memory import InMemoryHost, ServiceClient
from tests.agent_fakes import FakeToolHandler, ScriptedChatModel

__all__ = [
    "AGENT_JOBS",
    "CHAT_SERVICE",
    "CONVERSATION",
    "JOB_CONTRACTS",
    "MAP_CONTRACTS",
    "MAP_TOOLS",
    "SCRIPTED_MODEL_ID",
    "STEP_TIMEOUT_S",
    "SURVEY_CONTRACTS",
    "SURVEY_TOOLS",
    "ChatRig",
    "EmptyWorkspace",
    "NoGlbs",
    "TurnStream",
    "a_chat_rig",
    "a_jpeg",
    "a_turn",
    "eventually",
    "finished_call",
    "kinds",
    "text_of",
    "turn_event",
]

CHAT_SERVICE = chat_pb2.DESCRIPTOR.services_by_name["ChatService"]
AGENT_JOBS = jobs_pb2.DESCRIPTOR.services_by_name["AgentJobs"]
SURVEY_TOOLS = survey_tools_pb2.DESCRIPTOR.services_by_name["SurveyTools"]
MAP_TOOLS = map_tools_pb2.DESCRIPTOR.services_by_name["MapTools"]
SURVEY_CONTRACTS: tuple[ToolContract, ...] = tool_contracts(SURVEY_TOOLS)
MAP_CONTRACTS: tuple[ToolContract, ...] = tool_contracts(MAP_TOOLS)
JOB_CONTRACTS: tuple[ToolContract, ...] = tool_contracts(AGENT_JOBS)

CONVERSATION = "conv-1"
SCRIPTED_MODEL_ID = "ollama:scripted"
"""The id the rig's model factory builds the scripted model for."""
STEP_TIMEOUT_S = 10.0
"""The longest any one wait in these tests may take before it fails."""


# --- the rig -------------------------------------------------------------------------------


def _scripted_factory(model: BaseChatModel) -> Callable[[str], BaseChatModel]:
    def build(model_id: str) -> BaseChatModel:
        if not model_id.startswith("ollama:"):
            raise UnknownModelProvider(f"unknown model provider in {model_id!r}")
        return model

    return build


def _tool_factory(
    handlers: Mapping[str, FakeToolHandler],
) -> Callable[[JobRunner], Sequence[BoundTool]]:
    by_name = {contract.name: contract for contract in SURVEY_CONTRACTS}

    def tools(runner: JobRunner) -> Sequence[BoundTool]:
        bound = [
            bind_contract_tool(by_name[name], handler, runner) for name, handler in handlers.items()
        ]
        return [*bound, *job_tools(runner, JOB_CONTRACTS)]

    return tools


@dataclass(frozen=True)
class ChatRig:
    """A hub mounted in memory, the scripted model it answers with, and its tool handlers."""

    hub: ChatHub
    host: InMemoryHost[None]
    model: ScriptedChatModel
    tools: Mapping[str, FakeToolHandler]

    @property
    def chat(self) -> ServiceClient:
        return self.host.client(CHAT_SERVICE)

    @property
    def jobs(self) -> ServiceClient:
        return self.host.client(AGENT_JOBS)

    def tool(self, name: str) -> FakeToolHandler:
        return self.tools[name]


@asynccontextmanager
async def a_chat_rig(
    model: ScriptedChatModel,
    *,
    models: Sequence[ModelInfo] = (ModelInfo(SCRIPTED_MODEL_ID, "ollama", "scripted"),),
    default_model_id: str = SCRIPTED_MODEL_ID,
    **tools: FakeToolHandler,
) -> AsyncIterator[ChatRig]:
    """`ChatService` and `AgentJobs` over a hub whose conversations call `tools` (by tool
    name) plus the four job tools; the hub is closed on exit."""
    hub = ChatHub(
        model_factory=_scripted_factory(model),
        tools=_tool_factory(tools),
        models=lambda: models,
        default_model_id=default_model_id,
    )
    description: ServerDescription[None] = ServerDescription(
        services=(
            chat_service_module(chat_handlers(hub)),
            agent_jobs_module(agent_jobs_handlers(hub)),
        )
    )
    host = InMemoryHost(description, None)
    try:
        yield ChatRig(hub=hub, host=host, model=model, tools=tools)
    finally:
        await hub.close()


# --- reading streams -----------------------------------------------------------------------


def turn_event(message: Message) -> chat_pb2.TurnEvent:
    assert isinstance(message, chat_pb2.TurnEvent), f"not a TurnEvent: {message!r}"
    return message


async def a_turn(
    rig: ChatRig, text: str, *, model_id: str | None = None
) -> list[chat_pb2.TurnEvent]:
    """Every event of one `StreamTurn` on the rig's conversation."""
    request = chat_pb2.StreamTurnRequest(conversation_id=CONVERSATION, text=text, model_id=model_id)

    async def read() -> list[chat_pb2.TurnEvent]:
        return [turn_event(m) async for m in rig.chat.server_stream("StreamTurn", request)]

    return await asyncio.wait_for(read(), STEP_TIMEOUT_S)


class TurnStream:
    """A server stream read in the background, so the test can act while it runs."""

    def __init__(self, stream: AsyncIterator[Message]) -> None:
        self.events: list[chat_pb2.TurnEvent] = []
        self._arrived = asyncio.Condition()
        self._ended = False
        self._task = asyncio.ensure_future(self._read(stream))

    @classmethod
    def of_turn(cls, rig: ChatRig, text: str) -> TurnStream:
        request = chat_pb2.StreamTurnRequest(conversation_id=CONVERSATION, text=text)
        return cls(rig.chat.server_stream("StreamTurn", request))

    @classmethod
    def watching(cls, rig: ChatRig) -> TurnStream:
        request = chat_pb2.WatchConversationRequest(conversation_id=CONVERSATION)
        return cls(rig.chat.server_stream("WatchConversation", request))

    async def _read(self, stream: AsyncIterator[Message]) -> None:
        try:
            async for message in stream:
                async with self._arrived:
                    self.events.append(turn_event(message))
                    self._arrived.notify_all()
        finally:
            async with self._arrived:
                self._ended = True
                self._arrived.notify_all()

    async def until(self, kind: str) -> chat_pb2.TurnEvent:
        """The first event of this kind (`TurnEvent.event` oneof name), once it arrives."""

        async def first() -> chat_pb2.TurnEvent:
            async with self._arrived:
                await self._arrived.wait_for(lambda: self._first(kind) is not None or self._ended)
            found = self._first(kind)
            assert found is not None, f"the stream ended without a {kind}: {kinds(self.events)}"
            return found

        return await asyncio.wait_for(first(), STEP_TIMEOUT_S)

    async def turn(self) -> list[chat_pb2.TurnEvent]:
        """The events up to and including the first `turn_finished`."""
        finished = await self.until("turn_finished")
        return self.events[: self.events.index(finished) + 1]

    def _first(self, kind: str) -> chat_pb2.TurnEvent | None:
        return next((e for e in self.events if e.WhichOneof("event") == kind), None)


async def eventually(condition: Callable[[], bool]) -> None:
    """Return once `condition` holds, checking every 10 ms."""

    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), STEP_TIMEOUT_S)


# --- reading events ------------------------------------------------------------------------


def kinds(events: Sequence[chat_pb2.TurnEvent]) -> list[str]:
    """The oneof kind of each event, runs of the same kind collapsed to one."""
    collapsed: list[str] = []
    for event in events:
        kind = str(event.WhichOneof("event"))
        if not collapsed or collapsed[-1] != kind:
            collapsed.append(kind)
    return collapsed


def text_of(events: Sequence[chat_pb2.TurnEvent]) -> str:
    """The answer text the events stream, joined."""
    return "".join(e.text_delta for e in events if e.WhichOneof("event") == "text_delta")


def finished_call(events: Sequence[chat_pb2.TurnEvent], call_id: str) -> chat_pb2.ToolCallFinished:
    found = [
        e.tool_call_finished
        for e in events
        if e.WhichOneof("event") == "tool_call_finished" and e.tool_call_finished.call_id == call_id
    ]
    assert len(found) == 1, f"{call_id} finished {len(found)} times: {kinds(events)}"
    return found[0]


# --- a station with nothing recorded --------------------------------------------------------


class EmptyWorkspace:
    """A `SurveyWorkspace` with no scenes, runs or frames, for tests that inject the tool
    handlers and only need the frame route to have something to read."""

    def scenes(self) -> Sequence[SceneInfo]:
        return ()

    async def run_demo(
        self, dataset: str, prompt: str | None, *, max_frames: int | None, fps: float | None
    ) -> RunInfo:
        raise KeyError(dataset)

    def run(self, run_id: str) -> RunInfo | None:
        return None

    def timeline(self, run_id: str) -> Sequence[FrameRecord]:
        return ()

    async def detect(
        self, run_id: str, concept: str, frame_ids: Sequence[int]
    ) -> Sequence[FrameDetections]:
        raise KeyError(run_id)

    def objects(self, run_id: str) -> Sequence[StoredObject]:
        return ()

    def object_box(self, run_id: str, object_id: str, frame_id: int) -> ObjectBox | None:
        return None

    def frame(self, run_id: str, frame_id: int) -> FrameImage | None:
        return None

    def publish_geometry(self, run_id: str, obj: StoredObject) -> str:
        raise KeyError(obj.object_id)

    def datasets(self) -> Sequence[GalleryEntry]:
        return ()

    def dataset(self, dataset_id: str) -> GalleryEntry | None:
        return None

    async def prepare_dataset(self, dataset_id: str) -> GalleryEntry:
        raise KeyError(dataset_id)

    def dataset_thumbnail(self, dataset_id: str) -> bytes | None:
        return None

    async def run_rtabmap(
        self, dataset: str, *, max_frames: int | None, fps: float | None
    ) -> RunInfo:
        raise KeyError(dataset)

    async def run_sam_on_dataset(
        self, dataset: str, concept: str | None, *, max_frames: int | None
    ) -> Sequence[FrameDetections]:
        raise KeyError(dataset)


class NoGlbs:
    """A `GlbReader` with nothing published."""

    def uri(self, run_id: str, object_id: str) -> str:
        return f"mem://{run_id}/{object_id}"

    def read(self, uri: str) -> bytes | None:
        return None


# --- data ----------------------------------------------------------------------------------


def a_jpeg(size: tuple[int, int] = (64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (120, 80, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()
