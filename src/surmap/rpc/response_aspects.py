"""Response-aspect vocabulary and ASGI middleware — product-blind.

A `ResponseAspect` describes one response header: its name, how its value resolves
from the inbound request headers, and how successive values merge (hop append vs.
replace). `with_response_aspects(app, aspects)` wraps any ASGI app so that every
HTTP response's single `http.response.start` gains one header per aspect whose
resolution produced a value. A header the inner app already set is never
overridden (append-only). Websocket scopes pass through with `send` unwrapped —
they carry no `http.response.start`.

The kit imports no product package: uuid generation and hop merging are the
registrations' business, not the middleware's. The middleware calls `resolve`
and `merge` and writes what they return.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

__all__ = ["ResponseAspect", "with_response_aspects"]

AsgiApp = Callable[..., Awaitable[None]]


@runtime_checkable
class ResponseAspect(Protocol):
    """One response header the middleware appends to every HTTP response.

    `resolve` reads the value this aspect contributes from the inbound request
    headers (lowercased keys); returning `None` means the aspect adds nothing to
    this response. `merge` combines the inbound header value (`existing`, `None`
    when the request carried none) with the resolved value — hop-append for
    `X-Seen-By`, replace for `x-request-id`.
    """

    header: str

    def resolve(self, inbound: Mapping[str, str]) -> str | None: ...

    def merge(self, existing: str | None, resolved: str) -> str: ...


def _inbound_headers(scope: Mapping[str, Any]) -> dict[str, str]:
    """The request's headers, lowercased — the aspect `resolve`/`merge` vocabulary."""
    return {name.decode().lower(): value.decode() for name, value in scope.get("headers", ())}


def _existing_response_headers(message: Mapping[str, Any]) -> dict[str, str]:
    """The response start's already-set headers, lowercased — for the append-only check."""
    return {name.decode().lower(): value.decode() for name, value in message.get("headers", ())}


def with_response_aspects(app: AsgiApp, aspects: Sequence[ResponseAspect]) -> AsgiApp:
    """Wrap `app` so every HTTP response carries each aspect's header.

    On an HTTP scope, `send` is wrapped so the first `http.response.start` gains one
    header per aspect whose `resolve` produced a value. A header the inner app already
    set is left in place (append-only). `merge` combines the inbound header value
    with the resolved value. Only the first `http.response.start` is touched — the
    ASGI contract allows exactly one, and a pathological second passes through
    unchanged. On a websocket scope, `send` is unwrapped: websocket handshakes carry
    no `http.response.start` and pass through byte-identical.
    """

    async def wrapped(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            # Websocket (and any non-http) scopes pass through with `send` unwrapped.
            await app(scope, receive, send)
            return

        inbound = _inbound_headers(scope)
        first_start_seen = False

        async def aspect_send(message: dict[str, Any]) -> None:
            nonlocal first_start_seen
            if message["type"] == "http.response.start" and not first_start_seen:
                first_start_seen = True
                headers = list(message.get("headers", []))
                already_set = _existing_response_headers(message)
                for aspect in aspects:
                    header_lower = aspect.header.lower()
                    if header_lower in already_set:
                        # Append-only: the inner app set this header; never override it.
                        continue
                    resolved = aspect.resolve(inbound)
                    if resolved is None:
                        continue
                    final = aspect.merge(inbound.get(header_lower), resolved)
                    headers.append((aspect.header.encode(), final.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await app(scope, receive, aspect_send)

    return wrapped
