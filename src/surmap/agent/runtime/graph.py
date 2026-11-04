"""The per-turn LangGraph graph.

```text
          ┌──────── pending (steers, job notices) drained here
START ─► model ──(tool calls)──► tools ──► model … ──(no calls)──► END
            └─(round cap | repeated identical failures)──► cut_off ──► END
```

Tool calls of one model batch run one at a time through their `BoundTool`. `cut_off` answers
every unanswered call with a "Not run" tool result. There is no checkpointer: the session seeds
the history and appends what the turn adds.
"""

from __future__ import annotations

import json
import operator
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolCall,
    ToolMessage,
)
from langchain_core.runnables import Runnable
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from surmap.agent.runtime.events import (
    FinishReason,
    SteerApplied,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
)
from surmap.agent.runtime.jobs import Completed, Detached, Failed, ToolOutcome
from surmap.agent.runtime.tools import BoundTool

__all__ = [
    "KIND_KEY",
    "MAX_ROUNDS_ENV",
    "NOTICE_KIND",
    "STEER_DETACH_REASON",
    "STEER_KIND",
    "SUBAGENT_KIND",
    "PendingDrain",
    "TurnCaps",
    "TurnGraph",
    "TurnState",
    "build_turn_graph",
    "turn_input",
]

MAX_ROUNDS_ENV = "SURMAP_AGENT_MAX_ROUNDS"

STEER_DETACH_REASON = "detached by steer"
"""The detail of a call that a steer detached; `AgentSession.steer` hands it to the runner."""
KIND_KEY = "surmap_kind"
"""The `additional_kwargs` key that marks a pending message as a steer or a notice."""
STEER_KIND = "steer"
NOTICE_KIND = "job_notice"
SUBAGENT_KIND = "subagent_message"
"""A subagent's message to the conversation that started it."""

PendingDrain = Callable[[], Sequence[BaseMessage]]
"""Takes the messages queued since the last call (notices, then steers), oldest first."""


@dataclass(frozen=True)
class TurnCaps:
    """Where a runaway turn is cut off."""

    max_rounds: int = 30
    """Tool rounds a turn may run; the model call asking for more is answered "Not run"."""
    max_identical_failures: int = 3
    """Failures of the same tool with the same arguments before the turn is cut off."""

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> TurnCaps:
        """The defaults, with `max_rounds` from `SURMAP_AGENT_MAX_ROUNDS` when it is set.

        Raises `ValueError` for a value that is not a positive integer.
        """
        caps = cls()
        raw = env.get(MAX_ROUNDS_ENV)
        if raw is None:
            return caps
        try:
            rounds = int(raw)
        except ValueError:
            rounds = 0
        if rounds < 1:
            raise ValueError(f"{MAX_ROUNDS_ENV} must be a positive integer, not {raw!r}")
        return cls(max_rounds=rounds, max_identical_failures=caps.max_identical_failures)


class TurnState(TypedDict):
    """The graph's state for one turn."""

    messages: Annotated[list[BaseMessage], operator.add]
    """The conversation so far plus what this turn added."""
    rounds: int
    """Tool rounds run so far in this turn."""
    finish_reason: FinishReason | None
    """Set by the node that ends the turn."""


TurnGraph = CompiledStateGraph[TurnState, None, TurnState, TurnState]


def turn_input(messages: Sequence[BaseMessage]) -> TurnState:
    """The state a turn starts from: the history to answer, no rounds run, no reason yet."""
    return {"messages": list(messages), "rounds": 0, "finish_reason": None}


def build_turn_graph(
    model: BaseChatModel,
    tools: Sequence[BoundTool],
    pending: PendingDrain,
    caps: TurnCaps,
) -> TurnGraph:
    """Compile the turn graph for `model` bound to `tools`."""
    by_name = {tool.name: tool for tool in tools}
    bound = model.bind_tools([tool.model_schema() for tool in tools]) if tools else model

    async def call_model(state: TurnState) -> dict[str, list[BaseMessage]]:
        drained = list(pending())
        writer = get_stream_writer()
        for message in drained:
            if message.additional_kwargs.get(KIND_KEY) == STEER_KIND:
                writer(SteerApplied(text=message.text, detached_call_ids=_detached(state)))
        reply = await _stream_reply(bound, [*state["messages"], *drained])
        return {"messages": [*drained, reply]}

    async def run_tools(state: TurnState) -> dict[str, object]:
        calls = _last_calls(state["messages"])
        writer = get_stream_writer()
        answers: list[BaseMessage] = []
        for call in calls:
            answers.append(await _run_call(by_name, call, writer))
        return {"messages": answers, "rounds": state["rounds"] + 1}

    def cut_off(state: TurnState) -> dict[str, object]:
        reason: FinishReason = (
            "repeated_failure"
            if _repeated_failure(state["messages"], caps.max_identical_failures)
            else "round_cap"
        )
        note = (
            "Not run: this turn made the same failing call too often."
            if reason == "repeated_failure"
            else "Not run: this turn reached its limit of tool rounds."
        )
        answers: list[BaseMessage] = [
            ToolMessage(
                content=note, tool_call_id=str(call["id"]), name=call["name"], status="error"
            )
            for call in _last_calls(state["messages"])
        ]
        return {"messages": answers, "finish_reason": reason}

    def after_model(state: TurnState) -> Literal["tools", "cut_off", "done"]:
        if not _last_calls(state["messages"]):
            return "done"
        if _repeated_failure(state["messages"], caps.max_identical_failures):
            return "cut_off"
        if state["rounds"] >= caps.max_rounds:
            return "cut_off"
        return "tools"

    def finish_stop(state: TurnState) -> dict[str, object]:
        return {"finish_reason": "stop"}

    graph = StateGraph(TurnState)
    graph.add_node("model", call_model)
    graph.add_node("tools", run_tools)
    graph.add_node("cut_off", cut_off)
    graph.add_node("done", finish_stop)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", after_model)
    graph.add_edge("tools", "model")
    graph.add_edge("cut_off", END)
    graph.add_edge("done", END)
    return graph.compile()


async def _stream_reply(
    model: Runnable[LanguageModelInput, AIMessage], messages: list[BaseMessage]
) -> AIMessage:
    """One model call, its text streamed to the turn as `TextDelta`s, as a whole `AIMessage`."""
    writer = get_stream_writer()
    whole: AIMessageChunk | None = None
    async for piece in model.astream(messages):
        if not isinstance(piece, AIMessageChunk):
            # A model that does not stream (Meta Responses) answers whole, in one piece.
            if piece.text:
                writer(TextDelta(piece.text))
            return piece
        if piece.text:
            writer(TextDelta(piece.text))
        whole = piece if whole is None else whole + piece
    if whole is None:
        return AIMessage(content="")
    return AIMessage(
        content=whole.content,
        tool_calls=whole.tool_calls,
        additional_kwargs=whole.additional_kwargs,
        response_metadata=whole.response_metadata,
        usage_metadata=whole.usage_metadata,
        id=whole.id,
    )


def _last_calls(messages: Sequence[BaseMessage]) -> list[ToolCall]:
    last = messages[-1] if messages else None
    return list(last.tool_calls) if isinstance(last, AIMessage) else []


async def _run_call(
    by_name: Mapping[str, BoundTool], call: ToolCall, writer: Callable[[object], None]
) -> ToolMessage:
    call_id, name = str(call["id"]), call["name"]
    tool = by_name.get(name)
    if tool is None:
        return ToolMessage(
            content=f"Unknown tool {name}.", tool_call_id=call_id, name=name, status="error"
        )
    try:
        prepared = tool.prepare(call["args"])
    except ValueError as error:
        return ToolMessage(
            content=f"Invalid arguments: {error}", tool_call_id=call_id, name=name, status="error"
        )
    writer(
        ToolCallStarted(
            call_id=call_id, tool=name, arguments=prepared.arguments, execution=prepared.execution
        )
    )
    outcome = await tool.run(prepared)
    writer(ToolCallFinished(call_id=call_id, tool=name, outcome=outcome))
    return ToolMessage(
        content=_content(outcome),
        tool_call_id=call_id,
        name=name,
        status="error" if isinstance(outcome, Failed) else "success",
        additional_kwargs={"detached": outcome.detail} if isinstance(outcome, Detached) else {},
    )


def _detached(state: TurnState) -> tuple[str, ...]:
    """The calls of the latest tool round that a steer detached."""
    ids: list[str] = []
    for message in reversed(state["messages"]):
        if not isinstance(message, ToolMessage):
            break
        if message.additional_kwargs.get("detached") == STEER_DETACH_REASON:
            ids.append(message.tool_call_id)
    return tuple(reversed(ids))


def _content(outcome: ToolOutcome) -> str:
    if isinstance(outcome, Completed):
        return json.dumps(outcome.result, default=str)
    if isinstance(outcome, Detached):
        return (
            f"Job {outcome.job.job_id} ({outcome.job.tool}) is still running: {outcome.detail}. "
            "Its result will arrive as a notice; use wait_for_jobs, get_job or cancel_job "
            f"with job_id {outcome.job.job_id}."
        )
    return f"Failed: {outcome.error}"


def _repeated_failure(messages: Sequence[BaseMessage], limit: int) -> bool:
    """Whether one tool call (same name, same arguments) has failed `limit` times this turn."""
    start = max(
        (
            index
            for index, message in enumerate(messages)
            if isinstance(message, HumanMessage) and "surmap_kind" not in message.additional_kwargs
        ),
        default=0,
    )
    calls = {
        call["id"]: (call["name"], json.dumps(call["args"], sort_keys=True, default=str))
        for message in messages[start:]
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    }
    failures: dict[tuple[str, str], int] = {}
    for message in messages[start:]:
        if isinstance(message, ToolMessage) and message.status == "error":
            key = calls.get(message.tool_call_id)
            if key is not None:
                failures[key] = failures.get(key, 0) + 1
    return any(count >= limit for count in failures.values())
