"""Builders shared by the agent's chat-model tests. Not collected by pytest.

The `echo` tool in each shape the adapters see it, the hand-built Meta Responses bodies in
`tests/fixtures/agent/meta_responses_<name>.json` (their function-call shape follows the
OpenAI-style Responses API until the live Muse check confirms Meta's) and readers for a Responses
request's `input` items. `round_trip` is the live driver: it lets a real model call `echo` once and
feeds the result back. The fake provider servers are `tests/fake_meta.py`,
`tests/fake_fireworks.py` and `tests/fake_ollama.py`.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool

__all__ = [
    "ECHO_PARAMETERS",
    "ECHO_PORTABLE_TOOL",
    "ECHO_RESPONSES_TOOL",
    "ROOF_JPEG_B64",
    "RoundTrip",
    "a_recorded_reply",
    "a_reply",
    "echo_tool",
    "input_types",
    "item_of_type",
    "round_trip",
]

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent"
ROOF_JPEG_B64 = base64.b64encode(b"\xff\xd8\xff\xe0 roof frame").decode("ascii")

ECHO_PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {"text": {"type": "string", "description": "What to repeat."}},
    "required": ["text"],
}
ECHO_PORTABLE_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "echo",
        "description": "Repeat the text back.",
        "parameters": ECHO_PARAMETERS,
    },
}
"""`echo` as the runtime hands it to `bind_tools` (`BoundTool.model_schema()`)."""
ECHO_RESPONSES_TOOL: dict[str, object] = {
    "type": "function",
    "name": "echo",
    "description": "Repeat the text back.",
    "parameters": ECHO_PARAMETERS,
    "strict": False,
}
"""`echo` as the Meta Responses API receives it."""


def _echo(text: str) -> str:
    return text


def echo_tool() -> StructuredTool:
    """A trivial tool that returns its `text` argument."""
    return StructuredTool.from_function(
        func=_echo, name="echo", description="Repeat the text back.", args_schema=ECHO_PARAMETERS
    )


# --- Meta Responses bodies ------------------------------------------------------------------


def a_recorded_reply(name: str) -> dict[str, object]:
    """The hand-built body `tests/fixtures/agent/meta_responses_<name>.json`."""
    loaded: object = json.loads((FIXTURES / f"meta_responses_{name}.json").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, object], loaded)


def a_reply(*output: Mapping[str, object], model: str | None = None) -> dict[str, object]:
    """A Responses body with these output items and a small usage block."""
    body: dict[str, object] = {
        "object": "response",
        "status": "completed",
        "output": [dict(item) for item in output],
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }
    if model is not None:
        body["model"] = model
    return body


def item_of_type(body: Mapping[str, object], item_type: str) -> list[dict[str, object]]:
    """Every `input` item of a request body with this `type`, in order."""
    items = body["input"]
    assert isinstance(items, list)
    return [
        cast(dict[str, object], item)
        for item in items
        if isinstance(item, dict) and item.get("type") == item_type
    ]


def input_types(body: Mapping[str, object]) -> list[str]:
    """The `type` of every `input` item of a request body, in order."""
    items = body["input"]
    assert isinstance(items, list)
    return [str(item.get("type")) for item in items if isinstance(item, dict)]


# --- live driver ----------------------------------------------------------------------------


@dataclass(frozen=True)
class RoundTrip:
    """What a model did when offered `echo`: its tool call, and its answer after the result."""

    call: AIMessage
    answer: AIMessage


ROUND_TRIP_PROMPT = (
    "Call the echo tool exactly once with text 'surmap-ping'. "
    "After it returns, reply with the text it returned and nothing else."
)


def round_trip(model: BaseChatModel) -> RoundTrip:
    """Offer `echo`, run the one call the model makes, and ask for its answer."""
    echo = echo_tool()
    bound = model.bind_tools([echo])
    history: list[BaseMessage] = [HumanMessage(content=ROUND_TRIP_PROMPT)]
    call = bound.invoke(history)
    assert call.tool_calls, f"the model answered without calling echo: {call.content!r}"
    first = call.tool_calls[0]
    result = echo.invoke(first["args"])
    history += [call, ToolMessage(content=str(result), tool_call_id=str(first["id"]))]
    return RoundTrip(call=call, answer=bound.invoke(history))
