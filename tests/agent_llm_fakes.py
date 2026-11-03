"""Test doubles and builders for the agent's chat models. Not collected by pytest.

`RecordingMetaTransport` replays Meta Responses bodies in order and records every request.
`FakeOllamaTags` answers `GET /api/tags`, or fails like a stopped server. The recorded bodies
live in `tests/fixtures/agent/meta_responses_<name>.json`; their function-call shape follows the
OpenAI-style Responses API until the live Muse check confirms Meta's. `round_trip` is the live
driver: it lets a real model call `echo` once and feeds the result back.
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
from langchain_core.runnables import RunnableBinding
from langchain_core.tools import StructuredTool
from pydantic import SecretStr

from surmap.agent.llm.meta import MetaResponsesChatModel, ReasoningEffort
from surmap.labelling.ollama import OllamaError
from surmap.usage import UsageSink

__all__ = [
    "ECHO_PARAMETERS",
    "ECHO_PORTABLE_TOOL",
    "ECHO_RESPONSES_TOOL",
    "FIXTURE_KEY",
    "ROOF_JPEG_B64",
    "FakeOllamaTags",
    "RecordingMetaTransport",
    "RoundTrip",
    "a_muse_model",
    "a_recorded_reply",
    "a_reply",
    "bound_tool_names",
    "echo_tool",
    "input_types",
    "item_of_type",
    "round_trip",
]

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent"
FIXTURE_KEY = "sk-fixture-agent-key"
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


class RecordingMetaTransport:
    """Stands in for `MetaMuseTransport`: replies in order, records every request."""

    def __init__(self, *replies: Mapping[str, object]) -> None:
        self._replies = list(replies)
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.bodies: list[dict[str, object]] = []

    @classmethod
    def replying(cls, *names: str) -> RecordingMetaTransport:
        """Replays the recorded bodies with these fixture names."""
        return cls(*(a_recorded_reply(name) for name in names))

    @property
    def calls(self) -> int:
        return len(self.bodies)

    @property
    def last_body(self) -> dict[str, object]:
        assert self.bodies, "no request was sent"
        return self.bodies[-1]

    def post_json(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, object]
    ) -> Mapping[str, object]:
        self.urls.append(url)
        self.headers.append(dict(headers))
        self.bodies.append(json.loads(json.dumps(body)))
        assert self._replies, f"no reply left for {url}"
        return self._replies.pop(0)


def a_muse_model(
    transport: RecordingMetaTransport,
    *,
    usage_sink: UsageSink | None = None,
    model: str = "muse-wonder-1.0",
    reasoning_effort: ReasoningEffort = "medium",
    max_output_tokens: int = 8192,
) -> MetaResponsesChatModel:
    """Muse over a recording transport, keyed with the fixture key."""
    return MetaResponsesChatModel(
        model=model,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        api_key=SecretStr(FIXTURE_KEY),
        transport=transport,
        usage_sink=usage_sink,
    )


# --- Ollama ---------------------------------------------------------------------------------


class FakeOllamaTags:
    """Answers `GET /api/tags` with these model names, or fails like a stopped server."""

    def __init__(self, *models: str, reachable: bool = True) -> None:
        self._models = models
        self._reachable = reachable
        self.urls: list[str] = []

    @classmethod
    def holding(cls, *models: str) -> FakeOllamaTags:
        return cls(*models)

    @classmethod
    def unreachable(cls) -> FakeOllamaTags:
        return cls(reachable=False)

    def get_json(self, url: str) -> Mapping[str, object]:
        self.urls.append(url)
        if not self._reachable:
            raise OllamaError("Ollama request failed — is `ollama serve` running on this machine?")
        return {
            "models": [
                {"name": name, "model": name, "size": 2_019_393_189} for name in self._models
            ]
        }


def bound_tool_names(bound: object) -> list[str]:
    """The function names a `bind_tools` result will send to its model."""
    assert isinstance(bound, RunnableBinding)
    tools = bound.kwargs["tools"]
    names: list[str] = []
    for tool in tools:
        function = tool.get("function", tool)
        names.append(str(function["name"]))
    return names


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
