"""A fake Meta Model API (Responses) on a real loopback socket. Not collected by pytest.

`serving(script)` runs a local HTTP stub of `POST /v1/responses` on the shared fake server core
(`tests/fake_llm_server.py`) and yields its base URL (`http://127.0.0.1:<port>/v1`). The adapter's
real transport (`UrllibMetaMuseTransport`, stdlib `http.client`) posts to it and parses real bytes.

What it proves is client ↔ stub agreement: the stub follows the Responses shape
`MetaResponsesChatModel` documents (`output` items `reasoning`, `message` with `output_text` parts,
`function_call` with `call_id` / `name` / JSON-string `arguments`; `usage` with
`output_tokens_details.reasoning_tokens`). Agreement with Meta itself is the gated live test
(`SURMAP_LIVE_META=1`).

- `POST /v1/responses` answers the script's next round as one whole JSON response (the adapter
  sends `"stream": false`). The last round repeats once the rounds are exhausted. A non-200
  `status` answers every request with an error body instead.
- Every request is recorded (method, path, headers, parsed JSON body) on the script.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

from surmap.rpc.description import HttpRoute
from surmap.rpc.http import HttpRequest, HttpResponse
from tests.fake_llm_server import ProviderScript, RecordedRequest, json_response, serving_routes

__all__ = [
    "FAKE_META_KEY",
    "FakeFunctionCall",
    "FakeMetaScript",
    "MetaRound",
    "answering",
    "calling",
    "reasoning_only",
    "serving",
]

FAKE_META_KEY = "sk-fake-meta-key-0123"


@dataclass(frozen=True)
class FakeFunctionCall:
    """One `function_call` item. `arguments` is sent as a JSON string; a `str` is sent verbatim."""

    call_id: str
    name: str
    arguments: Mapping[str, object] | str = field(default_factory=dict)


@dataclass(frozen=True)
class MetaRound:
    """One Responses reply: a reasoning item, then optional text, then function calls."""

    text: str | None = None
    calls: tuple[FakeFunctionCall, ...] = ()
    input_tokens: int = 812
    output_tokens: int = 64
    reasoning_tokens: int = 40


def answering(
    text: str, *, input_tokens: int = 812, output_tokens: int = 64, reasoning_tokens: int = 40
) -> MetaRound:
    """A round that answers with `text` (812 + 64 tokens, 40 of them reasoning, by default)."""
    return MetaRound(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def calling(name: str, call_id: str, **arguments: object) -> MetaRound:
    """A round that calls function `name` once with `arguments`."""
    return MetaRound(calls=(FakeFunctionCall(call_id=call_id, name=name, arguments=arguments),))


def reasoning_only() -> MetaRound:
    """A round that spent its whole output budget reasoning: neither text nor a call."""
    return MetaRound(output_tokens=8192, reasoning_tokens=8192)


@dataclass
class FakeMetaScript(ProviderScript[MetaRound]):
    """What the stub answers, and every request it received."""

    rounds: Sequence[MetaRound] = (MetaRound(text="ok"),)

    @property
    def responses_requests(self) -> list[RecordedRequest]:
        return self.requests_to("/responses")

    @property
    def last_request(self) -> RecordedRequest:
        sent = self.responses_requests
        assert sent, "no Responses request was sent"
        return sent[-1]


# --- reply bodies -----------------------------------------------------------------------------


def _output(reply: MetaRound, index: int) -> list[dict[str, object]]:
    items: list[dict[str, object]] = [
        {"type": "reasoning", "id": f"rs_fake_{index}", "summary": []}
    ]
    if reply.text is not None:
        items.append(
            {
                "type": "message",
                "id": f"msg_fake_{index}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": reply.text, "annotations": []}],
            }
        )
    for call in reply.calls:
        arguments = (
            call.arguments if isinstance(call.arguments, str) else json.dumps(dict(call.arguments))
        )
        items.append(
            {
                "type": "function_call",
                "id": f"fc_{call.call_id}",
                "call_id": call.call_id,
                "name": call.name,
                "arguments": arguments,
                "status": "completed",
            }
        )
    return items


def _response(reply: MetaRound, model: str, index: int) -> dict[str, object]:
    return {
        "id": f"resp_fake_{index}",
        "object": "response",
        "status": "completed",
        "model": model,
        "output": _output(reply, index),
        "usage": {
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
            "output_tokens_details": {"reasoning_tokens": reply.reasoning_tokens},
            "total_tokens": reply.input_tokens + reply.output_tokens,
        },
    }


def _error(status: int) -> dict[str, object]:
    return {"error": {"message": f"fake Meta error {status}", "code": status}}


# --- the stub ---------------------------------------------------------------------------------


def _routes(script: FakeMetaScript) -> tuple[HttpRoute[None], ...]:
    async def responses(request: HttpRequest) -> HttpResponse:
        recorded = script.record(request)
        if script.status != 200:
            return json_response(script.status, _error(script.status))
        model = str(recorded.body.get("model", ""))
        reply = script.next_round()
        return json_response(200, _response(reply, model, len(script.responses_requests)))

    return (HttpRoute(method="POST", path="/v1/responses", handler=lambda _c: responses),)


@contextmanager
def serving(script: FakeMetaScript) -> Iterator[str]:
    """Serve `script` on a loopback port in a background thread; yield its base URL."""
    with serving_routes(_routes(script), name="fake-meta") as root:
        yield f"{root}/v1"
