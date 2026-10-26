"""Third-party HTTP stubs as kit descriptions — the same hosts, no `http.server` thread."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from surmap.rpc.description import HttpRoute, ServerDescription
from surmap.rpc.http import HttpHandler

__all__ = ["aio_http_stub"]


def aio_http_stub(routes: Mapping[tuple[str, str], HttpHandler]) -> ServerDescription[Any]:
    """A description serving `{(method, path): handler}`.

    Use path ``*`` as a fallback when no exact ``(method, path)`` matches (after Connect RPC
    paths are ruled out). Test HTTP stubs use this for POST bodies that are not chat completions.
    """

    def _route_factory(handler: HttpHandler) -> Callable[[Any], HttpHandler]:
        return lambda _context: handler

    http_routes = tuple(
        HttpRoute(method, path, _route_factory(handler))
        for (method, path), handler in routes.items()
    )
    return ServerDescription(http_routes=http_routes)
