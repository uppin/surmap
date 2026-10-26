"""`with_response_aspects` — append aspect headers to every HTTP response, never override.

The middleware wraps any ASGI app. On an HTTP scope it wraps `send` so the first
`http.response.start` gains one header per aspect whose resolution produced a value;
a header the inner app already set is never overridden (append-only). On a websocket
scope the `send` callable is unwrapped — websocket handshakes carry no
`http.response.start` and pass through byte-identical.

These tests define the kit's product-blind vocabulary: a `ResponseAspect` describes one
response header (its name, how its value resolves from the inbound request headers,
how successive values merge), and `with_response_aspects(app, aspects)` is the
wrapper. The kit imports no product package — uuid generation and hop merging are
generic, exercised here through test-supplied aspect implementations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from surmap.rpc._listener import build_listener_app
from surmap.rpc.http import HttpRequest, HttpResponse
from surmap.rpc.response_aspects import ResponseAspect, with_response_aspects

# --------------------------------------------------------------------------- #
# Test vocabulary — concrete aspects the kit would never ship.               #
# --------------------------------------------------------------------------- #


class _ReplaceAspect:
    """A replace-semantics aspect: the resolved value wins (echo inbound or fallback)."""

    def __init__(self, header: str, fallback: str) -> None:
        self.header = header
        self._fallback = fallback

    def resolve(self, inbound: Mapping[str, str]) -> str | None:
        present = inbound.get(self.header) or inbound.get(self.header.lower())
        return present.strip() if present and present.strip() else self._fallback

    def merge(self, existing: str | None, resolved: str) -> str:
        return resolved


class _HopAppendAspect:
    """A hop-append aspect: uniq(existing hops + this hop), comma-joined, capped."""

    def __init__(self, header: str, this_hop: str, *, cap: int = 20) -> None:
        self.header = header
        self._this_hop = this_hop
        self._cap = cap

    def resolve(self, inbound: Mapping[str, str]) -> str | None:
        return self._this_hop

    def merge(self, existing: str | None, resolved: str) -> str:
        hops: list[str] = []
        if existing:
            hops.extend(h.strip() for h in existing.split(",") if h.strip())
        hops.append(resolved)
        seen: set[str] = set()
        unique: list[str] = []
        for hop in hops:
            if hop not in seen:
                seen.add(hop)
                unique.append(hop)
        if len(unique) <= self._cap:
            return ",".join(unique)
        # Cap: keep this service's hop (the resolved value, last) and the first
        # (cap-1) inbound hops — the originating hops are most informative,
        # the newest inbound hops are dropped first.
        return ",".join([*unique[: self._cap - 1], unique[-1]])


# --------------------------------------------------------------------------- #
# Bare ASGI drivers — no socket, fully deterministic.                        #
# --------------------------------------------------------------------------- #


def _scope(
    *,
    type_: str = "http",
    method: str = "GET",
    path: str = "/",
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    raw_headers: list[tuple[bytes, bytes]] = []
    for name, value in (headers or {}).items():
        raw_headers.append((name.encode(), value.encode()))
    scope: dict[str, Any] = {"type": type_, "method": method, "path": path, "headers": raw_headers}
    if type_ == "http":
        scope["query_string"] = b""
    return scope


async def _drive(
    app: Any, scope: dict[str, Any], *, request_body: bytes = b""
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Run `app` once, return (start_message, all_sent_messages)."""
    sent: list[dict[str, Any]] = []
    request_index = 0

    async def receive() -> dict[str, Any]:
        nonlocal request_index
        if request_index == 0:
            request_index += 1
            return {"type": "http.request", "body": request_body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    start = next((m for m in sent if m["type"] == "http.response.start"), None)
    return start, sent


def _headers_of(start: dict[str, Any] | None) -> dict[str, str]:
    assert start is not None, "no http.response.start was sent"
    return {name.decode(): value.decode() for name, value in start.get("headers", [])}


async def _bare_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """The simplest HTTP app: 200 with its own headers and body."""
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"ok", "more_body": False})


# --------------------------------------------------------------------------- #
# Append semantics — the core contract.                                      #
# --------------------------------------------------------------------------- #


async def test_aspect_headers_are_appended_to_the_inner_apps_response_start() -> None:
    aspects: Sequence[ResponseAspect] = (
        _ReplaceAspect("x-request-id", "fresh-id"),
        _HopAppendAspect("x-seen-by", "this-service"),
    )
    wrapped = with_response_aspects(_bare_app, aspects)

    start, _sent = await _drive(wrapped, _scope(headers={"x-request-id": "req-1"}))

    headers = _headers_of(start)
    assert headers["x-request-id"] == "req-1"
    assert headers["x-seen-by"] == "this-service"
    # The inner app's own header is preserved verbatim.
    assert headers["content-type"] == "text/plain"


async def test_a_header_the_inner_app_already_set_is_never_overridden() -> None:
    async def sets_request_id(scope: dict[str, Any], receive: Any, send: Any) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"x-request-id", b"inner-set-id"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    aspects: Sequence[ResponseAspect] = (_ReplaceAspect("x-request-id", "fresh-id"),)
    wrapped = with_response_aspects(sets_request_id, aspects)

    start, _sent = await _drive(wrapped, _scope(headers={"x-request-id": "req-1"}))

    headers = _headers_of(start)
    assert headers["x-request-id"] == "inner-set-id"


async def test_no_aspect_header_is_added_when_resolve_returns_none() -> None:
    class _NeverAspect:
        header = "x-never"

        def resolve(self, inbound: Mapping[str, str]) -> str | None:
            return None

        def merge(self, existing: str | None, resolved: str) -> str:
            return resolved

    aspects: Sequence[ResponseAspect] = (_NeverAspect(),)
    wrapped = with_response_aspects(_bare_app, aspects)

    start, _sent = await _drive(wrapped, _scope())

    assert "x-never" not in _headers_of(start)


# --------------------------------------------------------------------------- #
# Resolution — inbound echo vs. resolver fallback.                           #
# --------------------------------------------------------------------------- #


async def test_a_present_inbound_request_id_is_echoed_verbatim() -> None:
    aspects: Sequence[ResponseAspect] = (_ReplaceAspect("x-request-id", "fresh-id"),)
    wrapped = with_response_aspects(_bare_app, aspects)

    start, _sent = await _drive(wrapped, _scope(headers={"x-request-id": "req-abc"}))

    assert _headers_of(start)["x-request-id"] == "req-abc"


async def test_an_absent_inbound_request_id_yields_the_resolvers_fallback() -> None:
    aspects: Sequence[ResponseAspect] = (_ReplaceAspect("x-request-id", "fresh-id"),)
    wrapped = with_response_aspects(_bare_app, aspects)

    start, _sent = await _drive(wrapped, _scope())

    assert _headers_of(start)["x-request-id"] == "fresh-id"


# --------------------------------------------------------------------------- #
# Merge semantics — hop append with uniq and 20-entry cap.                   #
# --------------------------------------------------------------------------- #


async def test_seen_by_appends_this_hop_to_inbound_hops() -> None:
    aspects: Sequence[ResponseAspect] = (_HopAppendAspect("x-seen-by", "this-service"),)
    wrapped = with_response_aspects(_bare_app, aspects)

    start, _sent = await _drive(wrapped, _scope(headers={"x-seen-by": "upstream-a,upstream-b"}))

    assert _headers_of(start)["x-seen-by"] == "upstream-a,upstream-b,this-service"


async def test_seen_by_deduplicates_repeated_hops() -> None:
    aspects: Sequence[ResponseAspect] = (_HopAppendAspect("x-seen-by", "this-service"),)
    wrapped = with_response_aspects(_bare_app, aspects)

    start, _sent = await _drive(
        wrapped, _scope(headers={"x-seen-by": "this-service,upstream-a,this-service"})
    )

    assert _headers_of(start)["x-seen-by"] == "this-service,upstream-a"


async def test_seen_by_caps_at_twenty_unique_entries() -> None:
    inbound_hops = ",".join(f"hop-{i:02d}" for i in range(25))
    aspects: Sequence[ResponseAspect] = (_HopAppendAspect("x-seen-by", "this-service"),)
    wrapped = with_response_aspects(_bare_app, aspects)

    start, _sent = await _drive(wrapped, _scope(headers={"x-seen-by": inbound_hops}))

    value = _headers_of(start)["x-seen-by"]
    entries = value.split(",")
    assert len(entries) == 20
    assert entries[-1] == "this-service"
    # The first 19 unique inbound hops are kept, this-service is appended as the 20th.
    assert entries[:19] == [f"hop-{i:02d}" for i in range(19)]


async def test_seen_by_with_no_inbound_hops_carries_only_this_service() -> None:
    aspects: Sequence[ResponseAspect] = (_HopAppendAspect("x-seen-by", "this-service"),)
    wrapped = with_response_aspects(_bare_app, aspects)

    start, _sent = await _drive(wrapped, _scope())

    assert _headers_of(start)["x-seen-by"] == "this-service"


# --------------------------------------------------------------------------- #
# Websocket scopes — pass through untouched.                                 #
# --------------------------------------------------------------------------- #


async def test_a_websocket_scope_passes_through_with_send_unwrapped() -> None:
    received: list[dict[str, Any]] = []

    async def ws_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        # The middleware must not wrap `send` for websocket scopes; the app sees
        # the original callable and emits the accept message itself.
        received.append(scope)
        await send({"type": "websocket.accept", "headers": []})

    aspects: Sequence[ResponseAspect] = (_ReplaceAspect("x-request-id", "fresh-id"),)
    wrapped = with_response_aspects(ws_app, aspects)

    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "websocket.connect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await wrapped(_scope(type_="websocket", path="/_workers/connect"), receive, send)

    assert received, "the websocket app was not invoked"
    assert sent == [{"type": "websocket.accept", "headers": []}]
    # No http.response.start was synthesized by the middleware on a websocket scope.
    assert all(m["type"] != "http.response.start" for m in sent)


# --------------------------------------------------------------------------- #
# Multiple http.response.start safety — only the first is touched.           #
# --------------------------------------------------------------------------- #


async def test_only_the_first_http_response_start_is_touched() -> None:
    async def two_starts_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        first = {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
        await send(first)
        # A pathological second start (the ASGI contract allows exactly one; the
        # middleware must not corrupt it by appending a second time).
        second = {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"x-other", b"keep-me")],
        }
        await send(second)
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    aspects: Sequence[ResponseAspect] = (_ReplaceAspect("x-request-id", "fresh-id"),)
    wrapped = with_response_aspects(two_starts_app, aspects)

    _start, sent = await _drive(wrapped, _scope())

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) >= 2
    first_headers = {n.decode(): v.decode() for n, v in starts[0]["headers"]}
    second_headers = {n.decode(): v.decode() for n, v in starts[1]["headers"]}
    # The aspect header is added to the first start only.
    assert first_headers["x-request-id"] == "fresh-id"
    assert "x-request-id" not in second_headers
    assert second_headers["x-other"] == "keep-me"


# --------------------------------------------------------------------------- #
# The kit listener's own bare error paths carry the aspects.                  #
# --------------------------------------------------------------------------- #


def _listener_app() -> Any:
    """The kit's `build_listener_app` with a health route and a POST echo.

    Bare 404/405/413 paths live in it.
    """

    async def health(_request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=200, body=b"Alive", headers={"content-type": "text/plain"})

    async def echo(request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=200, body=request.body, headers={"content-type": "text/plain"})

    return build_listener_app(
        connect_apps={},
        http_handlers={
            ("GET", "/health/is_alive"): health,
            ("POST", "/echo"): echo,
        },
    )


async def test_the_kit_listener_bare_404_carries_the_aspect_headers() -> None:
    aspects: Sequence[ResponseAspect] = (_ReplaceAspect("x-request-id", "fresh-id"),)
    wrapped = with_response_aspects(_listener_app(), aspects)

    start, _sent = await _drive(wrapped, _scope(method="GET", path="/no-such-path"))

    headers = _headers_of(start)
    assert start is not None and start["status"] == 404
    assert headers["x-request-id"] == "fresh-id"


async def test_the_kit_listener_bare_405_carries_the_aspect_headers() -> None:
    aspects: Sequence[ResponseAspect] = (_ReplaceAspect("x-request-id", "fresh-id"),)
    wrapped = with_response_aspects(_listener_app(), aspects)

    start, _sent = await _drive(wrapped, _scope(method="POST", path="/health/is_alive", headers={}))

    headers = _headers_of(start)
    assert start is not None and start["status"] == 405
    assert headers["x-request-id"] == "fresh-id"


async def test_the_kit_listener_bare_413_carries_the_aspect_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Shrink the listener's body limit so a small test body triggers the bare 413 path
    # without allocating 4 MiB. The listener calls `read_limited_body(receive)` with its
    # default max; patch the reference the listener holds to one with a tiny limit.
    import surmap.rpc._listener as _listener_mod
    from surmap.rpc.http_limits import read_limited_body as _original

    async def _small_limit(receive: Any, *, max_bytes: int = 8) -> bytes:
        return await _original(receive, max_bytes=max_bytes)

    monkeypatch.setattr(_listener_mod, "read_limited_body", _small_limit)

    aspects: Sequence[ResponseAspect] = (_ReplaceAspect("x-request-id", "fresh-id"),)
    wrapped = with_response_aspects(_listener_app(), aspects)

    # An oversized POST body drives `read_limited_body` into `RequestBodyTooLargeError`
    # → the listener's bare 413 path. The POST route exists, so dispatch reaches the body read.
    start, _sent = await _drive(
        wrapped,
        _scope(method="POST", path="/echo"),
        request_body=b"x" * 100,
    )

    headers = _headers_of(start)
    assert start is not None and start["status"] == 413
    assert headers["x-request-id"] == "fresh-id"


# --------------------------------------------------------------------------- #
# The vocabulary shape — ResponseAspect is a structural protocol.            #
# --------------------------------------------------------------------------- #


def test_response_aspect_is_a_protocol_an_aspect_can_satisfy_structurally() -> None:
    # A class that defines `header`, `resolve`, and `merge` satisfies the protocol
    # without inheriting from it — structural typing, the kit stays product-blind.
    aspect: ResponseAspect = _ReplaceAspect("x-demo", "fallback")
    assert aspect.header == "x-demo"
    assert aspect.resolve({"x-demo": "inbound"}) == "inbound"
    assert aspect.merge(None, "fallback") == "fallback"
