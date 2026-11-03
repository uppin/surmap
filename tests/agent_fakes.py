"""Test doubles for the agent runtime: a scripted chat model, fake tool handlers, and contracts.

`ScriptedChatModel` answers with scripted `AIMessage`s in order and repeats the last one, so a
model that keeps calling a tool runs into the round cap. It records every history it was given
and the names of the tools bound to it. `FakeToolHandler` returns, raises, or holds until the
test releases it; it records each call and whether it was cancelled. Nothing here sleeps.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolCall,
    ToolCallChunk,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from surmap.agent.contracts import ExecutionMode, ExecutionPolicy, OnTimeout, ToolContract
from surmap.agent.runtime.events import (
    FinishReason,
    TextDelta,
    ToolCallFinished,
    TurnError,
    TurnEvent,
    TurnFinished,
)
from surmap.agent.runtime.graph import TurnCaps
from surmap.agent.runtime.jobs import JobRunner, ToolHandler, ToolOutcome
from surmap.agent.runtime.session import AgentSession, InMemoryConversationStore
from surmap.agent.runtime.tools import bind_contract_tool, job_tools

__all__ = [
    "TIMEOUT_SCALE",
    "FakeToolHandler",
    "ScriptedChatModel",
    "SessionRig",
    "a_session",
    "a_tool_contract",
    "agent_job_contracts",
    "answer",
    "calling",
    "collect",
    "errors_in",
    "finish_reason",
    "human_texts",
    "mentions",
    "outcome_of",
    "resolve_locally",
    "text_deltas",
    "tool_call",
    "tool_message_for",
    "until_held",
]

# --- scripted model ------------------------------------------------------------------------


def tool_call(name: str, call_id: str, **arguments: object) -> ToolCall:
    """One tool call the scripted model makes."""
    return ToolCall(name=name, args=dict(arguments), id=call_id, type="tool_call")


def calling(*calls: ToolCall) -> AIMessage:
    """A model reply that asks for these tool calls and says nothing."""
    return AIMessage(content="", tool_calls=list(calls))


def answer(text: str) -> AIMessage:
    """A model reply that answers with text and calls no tool."""
    return AIMessage(content=text)


def _words(text: str) -> list[str]:
    """`"a b c"` → `["a ", "b ", "c"]`: the pieces a streamed answer arrives in."""
    pieces = text.split(" ")
    return [piece + " " for piece in pieces[:-1]] + [pieces[-1]]


def _tool_name(tool: object) -> str:
    if isinstance(tool, BaseTool):
        return tool.name
    if isinstance(tool, Mapping):
        function = tool.get("function")
        if isinstance(function, Mapping):
            return str(function.get("name"))
        return str(tool.get("name"))
    return getattr(tool, "__name__", repr(tool))


class ScriptedChatModel(BaseChatModel):
    """A chat model that replies from a script; streams text answers word by word."""

    script: list[AIMessage]
    histories: list[list[BaseMessage]] = Field(default_factory=list)
    """Every history the model was called with, in call order."""
    bound_tool_names: list[list[str]] = Field(default_factory=list)
    """The tool names of every `bind_tools` call, in call order."""

    @classmethod
    def replying(cls, *replies: AIMessage) -> ScriptedChatModel:
        return cls(script=list(replies))

    @property
    def _llm_type(self) -> str:
        return "scripted"

    @property
    def calls(self) -> int:
        """How many times the model has been called."""
        return len(self.histories)

    def history_of_call(self, number: int) -> list[BaseMessage]:
        """The history the model saw on its `number`-th call, from 1."""
        return self.histories[number - 1]

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        self.bound_tool_names.append([_tool_name(tool) for tool in tools])
        return self.bind(tools=list(tools), **kwargs)

    def _next_reply(self, messages: list[BaseMessage]) -> AIMessage:
        self.histories.append(list(messages))
        position = min(len(self.histories), len(self.script)) - 1
        return self.script[position]

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        reply = self._next_reply(messages)
        return ChatResult(generations=[ChatGeneration(message=reply.model_copy())])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, None, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        yield from self._chunks(self._next_reply(messages))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for chunk in self._chunks(self._next_reply(messages)):
            if run_manager is not None:
                await run_manager.on_llm_new_token(chunk.text, chunk=chunk)
            yield chunk

    @staticmethod
    def _chunks(reply: AIMessage) -> list[ChatGenerationChunk]:
        if reply.tool_calls:
            calls = [
                ToolCallChunk(
                    name=call["name"],
                    args=json.dumps(call["args"]),
                    id=call["id"],
                    index=index,
                    type="tool_call_chunk",
                )
                for index, call in enumerate(reply.tool_calls)
            ]
            return [
                ChatGenerationChunk(
                    message=AIMessageChunk(content=reply.text, tool_call_chunks=calls)
                )
            ]
        return [
            ChatGenerationChunk(message=AIMessageChunk(content=piece))
            for piece in _words(reply.text)
        ]


# --- history reading -----------------------------------------------------------------------


def tool_message_for(history: Sequence[BaseMessage], call_id: str) -> ToolMessage:
    """The last tool result in `history` answering the call `call_id`."""
    answers = [m for m in history if isinstance(m, ToolMessage) and m.tool_call_id == call_id]
    assert answers, f"no tool message answers {call_id}"
    return answers[-1]


def human_texts(history: Sequence[BaseMessage]) -> list[str]:
    """The text of every human message in `history`, oldest first."""
    return [m.text for m in history if isinstance(m, HumanMessage)]


# --- fake tool handlers --------------------------------------------------------------------


class FakeToolHandler:
    """A tool handler that returns, raises, or holds until released; records its calls."""

    def __init__(
        self,
        *,
        result: Mapping[str, object] | None = None,
        error: str | None = None,
        hold: bool = False,
    ) -> None:
        self.result: Mapping[str, object] = result if result is not None else {}
        self.error = error
        self.calls: list[Mapping[str, object]] = []
        self.started = asyncio.Event()
        """Set when the first call begins."""
        self.was_cancelled = False
        self._released = asyncio.Event()
        if not hold:
            self._released.set()

    @classmethod
    def returning(cls, result: Mapping[str, object]) -> FakeToolHandler:
        return cls(result=result)

    @classmethod
    def failing(cls, error: str) -> FakeToolHandler:
        return cls(error=error)

    @classmethod
    def holding(cls, result: Mapping[str, object] | None = None) -> FakeToolHandler:
        """Blocks every call until `release()`, then returns `result`."""
        return cls(result=result, hold=True)

    def release(self) -> None:
        self._released.set()

    async def __call__(self, arguments: Mapping[str, object]) -> Mapping[str, object]:
        self.calls.append(dict(arguments))
        self.started.set()
        try:
            await self._released.wait()
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise
        if self.error is not None:
            raise RuntimeError(self.error)
        return self.result


# --- contracts -----------------------------------------------------------------------------

_EXECUTION_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {
        "mode": {"enum": ["SYNC", "ASYNC"]},
        "timeout_s": {"type": "integer", "minimum": 0},
        "on_timeout": {"enum": ["FAIL", "DETACH"]},
    },
    "additionalProperties": False,
}


def a_tool_contract(
    name: str = "run_demo",
    *,
    mode: ExecutionMode = ExecutionMode.SYNC,
    timeout_s: int = 1,
    on_timeout: OnTimeout = OnTimeout.FAIL,
    properties: Mapping[str, object] | None = None,
    service: str = "surmap.agent.v1.SurveyTools",
) -> ToolContract:
    """A contract as n1 builds them from the protos, with only what a test cares about set."""
    method = "".join(part.title() for part in name.split("_"))
    return ToolContract(
        name=name,
        service=service,
        method=method,
        description=f"The {name} tool.",
        input_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {**(properties or {}), "execution": _EXECUTION_SCHEMA},
            "additionalProperties": False,
        },
        default_execution=ExecutionPolicy(mode=mode, timeout_s=timeout_s, on_timeout=on_timeout),
    )


def agent_job_contracts() -> tuple[ToolContract, ...]:
    """The four `AgentJobs` tools with the defaults `jobs.proto` declares."""
    service = "surmap.agent.v1.AgentJobs"
    return (
        a_tool_contract(
            "wait_for_jobs",
            timeout_s=300,
            service=service,
            properties={
                "job_ids": {"type": "array", "items": {"type": "string"}},
                "mode": {"enum": ["ALL", "ANY"]},
                "timeout_s": {"type": "integer", "minimum": 0, "maximum": 300},
            },
        ),
        a_tool_contract(
            "get_job", timeout_s=10, service=service, properties={"job_id": {"type": "string"}}
        ),
        a_tool_contract(
            "cancel_job", timeout_s=10, service=service, properties={"job_id": {"type": "string"}}
        ),
        a_tool_contract("list_jobs", timeout_s=10, service=service),
    )


def resolve_locally(contract: ToolContract, arguments: Mapping[str, object]) -> ExecutionPolicy:
    """Stands in for n1's `resolve_execution`: the default, with any `execution` field applied."""
    policy = contract.default_execution
    override = arguments.get("execution")
    if not isinstance(override, Mapping):
        return policy
    mode = override.get("mode")
    timeout_s = override.get("timeout_s")
    on_timeout = override.get("on_timeout")
    return ExecutionPolicy(
        mode=ExecutionMode(mode) if isinstance(mode, str) else policy.mode,
        timeout_s=timeout_s if isinstance(timeout_s, int) else policy.timeout_s,
        on_timeout=OnTimeout(on_timeout) if isinstance(on_timeout, str) else policy.on_timeout,
    )


# --- a session over real runtime parts -----------------------------------------------------

TIMEOUT_SCALE = 0.05
"""Seconds one policy `timeout_s` unit lasts in tests: a `timeout_s=1` call waits 0.05 s."""


@dataclass(frozen=True)
class SessionRig:
    """A real `AgentSession` with the scripted model, runner and store a test inspects."""

    session: AgentSession
    model: ScriptedChatModel
    runner: JobRunner
    store: InMemoryConversationStore

    @property
    def history(self) -> list[BaseMessage]:
        return self.store.history(self.session.conversation_id)


def a_session(
    model: ScriptedChatModel,
    *tools: tuple[ToolContract, ToolHandler],
    caps: TurnCaps | None = None,
) -> SessionRig:
    """A session whose model can call `tools` plus the four job tools."""
    runner = JobRunner(timeout_scale=TIMEOUT_SCALE)
    store = InMemoryConversationStore()
    bound = [
        bind_contract_tool(contract, handler, runner, resolve=resolve_locally)
        for contract, handler in tools
    ]
    bound.extend(job_tools(runner, agent_job_contracts(), resolve=resolve_locally))
    session = AgentSession(
        conversation_id="conv-1",
        model=model,
        tools=bound,
        runner=runner,
        store=store,
        caps=caps,
    )
    return SessionRig(session=session, model=model, runner=runner, store=store)


# --- reading turn events -------------------------------------------------------------------


async def collect(events: AsyncIterator[TurnEvent]) -> list[TurnEvent]:
    """Every event of a turn, up to and including its `TurnFinished`."""
    return [event async for event in events]


def finish_reason(events: Sequence[TurnEvent]) -> FinishReason:
    """Why the turn ended; the last event must be its `TurnFinished`."""
    last = events[-1]
    assert isinstance(last, TurnFinished), f"the turn ended with {last!r}"
    return last.reason


def text_deltas(events: Sequence[TurnEvent]) -> list[str]:
    return [event.text for event in events if isinstance(event, TextDelta)]


def outcome_of(events: Sequence[TurnEvent], call_id: str) -> ToolOutcome:
    """How the tool call `call_id` finished in this turn."""
    finished = [e for e in events if isinstance(e, ToolCallFinished) and e.call_id == call_id]
    assert len(finished) == 1, f"{call_id} finished {len(finished)} times"
    return finished[0].outcome


def errors_in(events: Sequence[TurnEvent]) -> list[str]:
    return [event.message for event in events if isinstance(event, TurnError)]


def mentions(message: BaseMessage, *phrases: str) -> bool:
    """Whether the message's text contains every phrase."""
    return all(phrase in message.text for phrase in phrases)


async def until_held(handler: FakeToolHandler, work: asyncio.Future[Any]) -> None:
    """Return once `handler` is holding a call; re-raise `work`'s failure if it ends first."""
    started = asyncio.ensure_future(handler.started.wait())
    done, _ = await asyncio.wait({started, work}, return_when=asyncio.FIRST_COMPLETED)
    if started in done:
        return
    started.cancel()
    work.result()
    raise AssertionError("the work ended before the handler was called")
