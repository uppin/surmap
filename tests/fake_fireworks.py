"""A fake Fireworks provider on a real loopback socket. Not collected by pytest.

`serving(script)` runs a local HTTP stub of Fireworks' OpenAI-compatible API on the shared fake
server core (`tests/fake_llm_server.py`: `HypercornHost` port 0, its own thread and event loop) and
yields its base URL (`http://127.0.0.1:<port>/v1`).
The adapter's real client (`ChatOpenAI` → `openai` → `httpx`) talks to it and parses real bytes, so
a client upgrade that changes the wire format fails a test.

What it proves is client ↔ stub agreement: the stub follows Fireworks' documented chat completions
format. Agreement with Fireworks itself is the gated live test (`SURMAP_LIVE_FIREWORKS=1`).

- `POST /v1/chat/completions` answers the script's next round — a whole `chat.completion` object,
  or, when the request has `"stream": true`, SSE `chat.completion.chunk` frames ending in
  `data: [DONE]`. The last round repeats once the rounds are exhausted. A non-200 `status`
  answers every chat request with an OpenAI-style error body instead.
- `GET /v1/models` answers `{"object": "list", "data": [{"id": …}]}` from `served_models`.
- Every request is recorded (method, path, headers, parsed JSON body) on the script.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

from surmap.rpc.description import HttpRoute
from surmap.rpc.http import HttpRequest, HttpResponse
from tests.fake_llm_server import (
    ProviderScript,
    RecordedRequest,
    a_closed_port,
    json_response,
    serving_routes,
)

__all__ = [
    "FAKE_FIREWORKS_KEY",
    "FAKE_FIREWORKS_MODEL",
    "FakeFireworksScript",
    "FakeToolCall",
    "RecordedRequest",
    "Round",
    "a_closed_base_url",
    "answering",
    "calling",
    "content_frame",
    "finish_frame",
    "role_frame",
    "serving",
    "tool_call_frame",
    "usage_frame",
]

FAKE_FIREWORKS_KEY = "fw-fake-test-key-0123"
FAKE_FIREWORKS_MODEL = "accounts/fireworks/models/llama-v3p3-70b-instruct"


@dataclass(frozen=True)
class FakeToolCall:
    """One function call in a reply: `arguments` is sent as a JSON string."""

    id: str
    name: str
    arguments: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Round:
    """One chat reply: text, tool calls, or both, and its token usage."""

    content: str | None = None
    tool_calls: tuple[FakeToolCall, ...] = ()
    prompt_tokens: int = 12
    completion_tokens: int = 7

    @property
    def finish_reason(self) -> str:
        return "tool_calls" if self.tool_calls else "stop"


def answering(text: str, *, prompt_tokens: int = 12, completion_tokens: int = 7) -> Round:
    """A round that answers with `text`."""
    return Round(content=text, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


def calling(name: str, call_id: str, **arguments: object) -> Round:
    """A round that calls tool `name` once with `arguments`."""
    return Round(tool_calls=(FakeToolCall(id=call_id, name=name, arguments=arguments),))


@dataclass
class FakeFireworksScript(ProviderScript[Round]):
    """What the stub answers, and every request it received."""

    rounds: Sequence[Round] = (Round(content="ok"),)
    served_models: Sequence[str] = ()

    @property
    def chat_requests(self) -> list[RecordedRequest]:
        return self.requests_to("/chat/completions")

    @property
    def last_chat(self) -> RecordedRequest:
        chats = self.chat_requests
        assert chats, "no chat request was sent"
        return chats[-1]


# --- reply bodies -----------------------------------------------------------------------------


def _usage(reply: Round) -> dict[str, int]:
    return {
        "prompt_tokens": reply.prompt_tokens,
        "completion_tokens": reply.completion_tokens,
        "total_tokens": reply.prompt_tokens + reply.completion_tokens,
    }


def _completion(reply: Round, model: str) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "content": reply.content}
    if reply.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(dict(call.arguments))},
            }
            for call in reply.tool_calls
        ]
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 1_762_128_000,
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": reply.finish_reason}],
        "usage": _usage(reply),
    }


def _chunk(model: str, choices: list[dict[str, object]], **extra: object) -> dict[str, object]:
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": 1_762_128_000,
        "model": model,
        "choices": choices,
        **extra,
    }


def role_frame(model: str) -> dict[str, object]:
    """The first streamed chunk: the assistant role, no content yet."""
    return _chunk(model, [{"index": 0, "delta": {"role": "assistant", "content": ""}}])


def content_frame(model: str, text: str) -> dict[str, object]:
    """A streamed piece of the answer's text."""
    return _chunk(model, [{"index": 0, "delta": {"content": text}}])


def tool_call_frame(model: str, index: int, call: FakeToolCall) -> dict[str, object]:
    """A streamed tool call, whole in one delta (id, name and JSON arguments)."""
    delta = {
        "tool_calls": [
            {
                "index": index,
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(dict(call.arguments))},
            }
        ]
    }
    return _chunk(model, [{"index": 0, "delta": delta}])


def finish_frame(model: str, finish_reason: str) -> dict[str, object]:
    """The chunk that ends the choice."""
    return _chunk(model, [{"index": 0, "delta": {}, "finish_reason": finish_reason}])


def usage_frame(model: str, reply: Round) -> dict[str, object]:
    """The trailing usage chunk `stream_options.include_usage` asks for: no choices."""
    return _chunk(model, [], usage=_usage(reply))


def _frames(reply: Round, model: str, *, with_usage: bool) -> list[dict[str, object]]:
    frames = [role_frame(model)]
    if reply.content:
        half = len(reply.content) // 2
        for piece in (reply.content[:half], reply.content[half:]):
            if piece:
                frames.append(content_frame(model, piece))
    for index, call in enumerate(reply.tool_calls):
        frames.append(tool_call_frame(model, index, call))
    frames.append(finish_frame(model, reply.finish_reason))
    if with_usage:
        frames.append(usage_frame(model, reply))
    return frames


def _sse(frames: list[dict[str, object]]) -> bytes:
    lines = [f"data: {json.dumps(frame)}\n\n" for frame in frames]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _error(status: int) -> dict[str, object]:
    kind = "authentication_error" if status in (401, 403) else "server_error"
    return {"error": {"message": f"fake Fireworks error {status}", "type": kind, "code": status}}


# --- the stub ---------------------------------------------------------------------------------


def _routes(script: FakeFireworksScript) -> tuple[HttpRoute[None], ...]:
    async def chat(request: HttpRequest) -> HttpResponse:
        script.record(request)
        if script.status != 200:
            return json_response(script.status, _error(script.status))
        body = script.last_chat.body
        model = str(body.get("model", ""))
        reply = script.next_round()
        if body.get("stream") is True:
            options = body.get("stream_options")
            with_usage = isinstance(options, dict) and options.get("include_usage") is True
            return HttpResponse(
                status=200,
                body=_sse(_frames(reply, model, with_usage=with_usage)),
                headers={"content-type": "text/event-stream"},
            )
        return json_response(200, _completion(reply, model))

    async def models(request: HttpRequest) -> HttpResponse:
        script.record(request)
        data = [{"id": name, "object": "model"} for name in script.served_models]
        return json_response(200, {"object": "list", "data": data})

    return (
        HttpRoute(method="POST", path="/v1/chat/completions", handler=lambda _c: chat),
        HttpRoute(method="GET", path="/v1/models", handler=lambda _c: models),
    )


@contextmanager
def serving(script: FakeFireworksScript) -> Iterator[str]:
    """Serve `script` on a loopback port in a background thread; yield its base URL."""
    with serving_routes(_routes(script), name="fake-fireworks") as root:
        yield f"{root}/v1"


def a_closed_base_url() -> str:
    """A loopback base URL nothing listens on: a port bound and released."""
    return f"http://127.0.0.1:{a_closed_port()}/v1"
