"""The core every fake LLM provider shares: a scripted HTTP stub on a real loopback socket.

Not collected by pytest. A provider module (`tests/fake_fireworks.py`, `tests/fake_meta.py`,
`tests/fake_ollama.py`) speaks one provider's wire format on top of it:

- `ProviderScript[R]` holds the scripted `rounds` (one answer per request; the last repeats once
  they run out), a `status` (non-200 answers with that provider's error body instead), and every
  request the stub received as a `RecordedRequest` (method, path, headers, parsed JSON body).
- `serving_routes(routes, name=…)` runs those routes on `HypercornHost` port 0 in its own thread
  and event loop and yields the root URL `http://127.0.0.1:<port>`; each provider appends its own
  base path.
- `a_closed_port()` is a loopback port nothing listens on, for "the server is down".

The adapter under test keeps its **real** client, pointed at the stub through its base-URL setting,
so a client upgrade that changes the bytes on the wire fails a test. What a fake proves is
client ↔ stub agreement with the provider's documented format; agreement with the provider itself
is the gated live test of each adapter.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from surmap.rpc.description import HttpRoute, ServerDescription
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.http import HttpRequest, HttpResponse

__all__ = [
    "ProviderScript",
    "RecordedRequest",
    "a_closed_port",
    "json_response",
    "serving_routes",
]

R = TypeVar("R")
_START_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class RecordedRequest:
    """One request the stub received."""

    method: str
    path: str
    headers: Mapping[str, str]
    body: Mapping[str, object]

    def header(self, name: str) -> str | None:
        """A header's value, looked up case-insensitively."""
        wanted = name.lower()
        for key, value in self.headers.items():
            if key.lower() == wanted:
                return value
        return None


@dataclass
class ProviderScript(Generic[R]):
    """What a fake provider answers, and every request it received."""

    rounds: Sequence[R] = ()
    status: int = 200
    """A non-200 status answers every scripted request with the provider's error body."""
    requests: list[RecordedRequest] = field(default_factory=list)
    _served: int = field(default=0, init=False, repr=False)

    def requests_to(self, path: str) -> list[RecordedRequest]:
        """The recorded requests whose path ends with `path`, in order."""
        return [r for r in self.requests if r.path.endswith(path)]

    def next_round(self) -> R:
        assert self.rounds, "the script has no rounds"
        index = min(self._served, len(self.rounds) - 1)
        self._served += 1
        return self.rounds[index]

    def record(self, request: HttpRequest) -> RecordedRequest:
        body: object = json.loads(request.body) if request.body else {}
        assert isinstance(body, dict), f"request body is not a JSON object: {request.body!r}"
        recorded = RecordedRequest(
            method=request.method,
            path=request.path,
            headers=dict(request.headers),
            body=body,
        )
        self.requests.append(recorded)
        return recorded


def json_response(status: int, payload: Mapping[str, object]) -> HttpResponse:
    """A JSON response with `status`."""
    return HttpResponse(
        status=status,
        body=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


@contextmanager
def serving_routes(routes: Sequence[HttpRoute[None]], *, name: str) -> Iterator[str]:
    """Serve `routes` on a loopback port in a background thread; yield `http://127.0.0.1:<port>`."""
    host = HypercornHost(ServerDescription[None](http_routes=tuple(routes)), None, port=0)
    loop = asyncio.new_event_loop()
    started = threading.Event()
    ports: list[int] = []
    failures: list[BaseException] = []

    def run() -> None:
        asyncio.set_event_loop(loop)
        try:
            ports.append(loop.run_until_complete(host.start()).public)
        except BaseException as exc:  # surfaced to the caller below
            failures.append(exc)
            started.set()
            return
        started.set()
        loop.run_forever()

    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    assert started.wait(_START_TIMEOUT_S), f"the {name} server did not start"
    if failures:
        raise failures[0]
    try:
        yield f"http://127.0.0.1:{ports[0]}"
    finally:
        asyncio.run_coroutine_threadsafe(host.stop(), loop).result(_START_TIMEOUT_S)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(_START_TIMEOUT_S)
        loop.close()


def a_closed_port() -> int:
    """A loopback port nothing listens on: bound and released."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port
