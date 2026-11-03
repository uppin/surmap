"""A fake Ollama server on a real loopback socket. Not collected by pytest.

`serving(script)` runs a local HTTP stub of the Ollama API on the shared fake server core
(`tests/fake_llm_server.py`) and yields its base URL (`http://127.0.0.1:<port>`, the shape
`SURMAP_OLLAMA_URL` takes). The adapters' real clients talk to it: `ChatOllama` → the `ollama`
package → `httpx` for chat, and `UrllibOllamaTagsTransport` (stdlib) for the model listing.

What it proves is client ↔ stub agreement with Ollama's documented API; agreement with a real
Ollama server is the gated live test (`SURMAP_LIVE_OLLAMA=1`).

- `POST /api/chat` answers the script's next round. With `"stream": false` it is one whole JSON
  reply; otherwise (Ollama's default) newline-delimited JSON frames — the text in pieces, any
  `tool_calls` (arguments as a JSON object, as Ollama sends them) in their own frame, then a
  `done` frame with `done_reason` and the token counts. The last round repeats once the rounds
  are exhausted. A non-200 `status` answers every chat request with `{"error": …}`.
- `GET /api/tags` answers `{"models": [{"name": …, "model": …}]}` from `held_models`.
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
    "FakeOllamaScript",
    "FakeOllamaToolCall",
    "OllamaRound",
    "a_closed_ollama_url",
    "answering",
    "calling",
    "serving",
]

_CREATED_AT = "2026-11-03T12:00:00.000000Z"


@dataclass(frozen=True)
class FakeOllamaToolCall:
    """One tool call: Ollama sends `arguments` as a JSON object and no call id."""

    name: str
    arguments: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OllamaRound:
    """One chat reply: text, tool calls, or both, and its token counts."""

    content: str = ""
    tool_calls: tuple[FakeOllamaToolCall, ...] = ()
    prompt_eval_count: int = 12
    eval_count: int = 7


def answering(text: str) -> OllamaRound:
    """A round that answers with `text`."""
    return OllamaRound(content=text)


def calling(name: str, **arguments: object) -> OllamaRound:
    """A round that calls tool `name` once with `arguments`."""
    return OllamaRound(tool_calls=(FakeOllamaToolCall(name=name, arguments=arguments),))


@dataclass
class FakeOllamaScript(ProviderScript[OllamaRound]):
    """What the stub answers, and every request it received."""

    rounds: Sequence[OllamaRound] = (OllamaRound(content="ok"),)
    held_models: Sequence[str] = ()
    tags_status: int = 200
    """A non-200 status answers `GET /api/tags` with an error body."""

    @property
    def chat_requests(self) -> list[RecordedRequest]:
        return self.requests_to("/api/chat")

    @property
    def last_chat(self) -> RecordedRequest:
        chats = self.chat_requests
        assert chats, "no chat request was sent"
        return chats[-1]

    @property
    def tags_requests(self) -> list[RecordedRequest]:
        return self.requests_to("/api/tags")


# --- reply bodies -----------------------------------------------------------------------------


def _message(content: str, calls: Sequence[FakeOllamaToolCall] = ()) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [
            {"function": {"name": call.name, "arguments": dict(call.arguments)}} for call in calls
        ]
    return message


def _frame(model: str, message: Mapping[str, object]) -> dict[str, object]:
    return {"model": model, "created_at": _CREATED_AT, "message": dict(message), "done": False}


def _done(model: str, reply: OllamaRound, message: Mapping[str, object]) -> dict[str, object]:
    return {
        **_frame(model, message),
        "done": True,
        "done_reason": "stop",
        "total_duration": 1_200_000_000,
        "load_duration": 50_000_000,
        "prompt_eval_count": reply.prompt_eval_count,
        "prompt_eval_duration": 300_000_000,
        "eval_count": reply.eval_count,
        "eval_duration": 800_000_000,
    }


def _whole(reply: OllamaRound, model: str) -> dict[str, object]:
    return _done(model, reply, _message(reply.content, reply.tool_calls))


def _frames(reply: OllamaRound, model: str) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    half = len(reply.content) // 2
    for piece in (reply.content[:half], reply.content[half:]):
        if piece:
            frames.append(_frame(model, _message(piece)))
    if reply.tool_calls:
        frames.append(_frame(model, _message("", reply.tool_calls)))
    frames.append(_done(model, reply, _message("")))
    return frames


def _ndjson(frames: Sequence[Mapping[str, object]]) -> bytes:
    return "".join(f"{json.dumps(dict(frame))}\n" for frame in frames).encode("utf-8")


# --- the stub ---------------------------------------------------------------------------------


def _routes(script: FakeOllamaScript) -> tuple[HttpRoute[None], ...]:
    async def chat(request: HttpRequest) -> HttpResponse:
        recorded = script.record(request)
        if script.status != 200:
            return json_response(script.status, {"error": f"fake Ollama error {script.status}"})
        model = str(recorded.body.get("model", ""))
        reply = script.next_round()
        if recorded.body.get("stream") is False:
            return json_response(200, _whole(reply, model))
        return HttpResponse(
            status=200,
            body=_ndjson(_frames(reply, model)),
            headers={"content-type": "application/x-ndjson"},
        )

    async def tags(request: HttpRequest) -> HttpResponse:
        script.record(request)
        if script.tags_status != 200:
            return json_response(script.tags_status, {"error": "fake Ollama tags error"})
        models = [
            {"name": name, "model": name, "size": 2_019_393_189} for name in script.held_models
        ]
        return json_response(200, {"models": models})

    return (
        HttpRoute(method="POST", path="/api/chat", handler=lambda _c: chat),
        HttpRoute(method="GET", path="/api/tags", handler=lambda _c: tags),
    )


@contextmanager
def serving(script: FakeOllamaScript) -> Iterator[str]:
    """Serve `script` on a loopback port in a background thread; yield its base URL."""
    with serving_routes(_routes(script), name="fake-ollama") as root:
        yield root


def a_closed_ollama_url() -> str:
    """An Ollama base URL nothing listens on, like a stopped `ollama serve`."""
    return f"http://127.0.0.1:{a_closed_port()}"
