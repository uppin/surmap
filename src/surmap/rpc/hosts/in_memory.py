"""A `ServerDescription` mounted in memory: in-process clients, no socket, no thread."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Mapping
from typing import Generic, TypeVar

from connectrpc.server import ConnectASGIApplication
from google.protobuf.descriptor import MethodDescriptor, ServiceDescriptor
from google.protobuf.message import Message

from surmap.rpc.asgi import (
    call_bidi,
    call_client_stream,
    call_server_stream,
    call_unary,
)
from surmap.rpc.compose import compose_service
from surmap.rpc.description import Closeable, ServerDescription
from surmap.rpc.http import HttpHandler, HttpRequest, HttpResponse

__all__ = ["InMemoryHost", "ServiceClient"]

C = TypeVar("C")


class ServiceClient:
    """Calls one mounted service's methods by name."""

    def __init__(self, app: ConnectASGIApplication[object], service: ServiceDescriptor) -> None:
        self._app = app
        self._service = service

    def _method(self, name: str) -> MethodDescriptor:
        return self._service.methods_by_name[name]

    async def unary(
        self, method: str, request: Message, headers: Mapping[str, str] | None = None
    ) -> Message:
        return await call_unary(self._app, self._method(method), request, headers)

    def server_stream(
        self, method: str, request: Message, headers: Mapping[str, str] | None = None
    ) -> AsyncIterator[Message]:
        return call_server_stream(self._app, self._method(method), request, headers)

    async def client_stream(
        self,
        method: str,
        requests: AsyncIterable[Message],
        headers: Mapping[str, str] | None = None,
    ) -> Message:
        return await call_client_stream(self._app, self._method(method), requests, headers)

    def bidi(
        self,
        method: str,
        requests: AsyncIterable[Message],
        headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[Message]:
        return call_bidi(self._app, self._method(method), requests, headers)


class InMemoryHost(Generic[C]):
    def __init__(self, description: ServerDescription[C], context: C) -> None:
        """Builds every service, route and closeable from `context` now."""
        self._description = description
        self._context = context
        self._closed = False
        self._apps: dict[str, ConnectASGIApplication[object]] = {}
        for module in description.services:
            bricks = list(module.bricks(context))
            self._apps[module.descriptor.full_name] = compose_service(module.descriptor, *bricks)
        self._http: dict[tuple[str, str], HttpHandler] = {
            (route.method.upper(), route.path): route.handler(context)
            for route in description.http_routes
        }
        self._closeables: list[Closeable] = list(description.closeables(context))
        self._paths: dict[str, set[str]] = {}
        for method, path in self._http:
            self._paths.setdefault(path, set()).add(method)

    def client(self, service: ServiceDescriptor) -> ServiceClient:
        app = self._apps.get(service.full_name)
        if app is None:
            raise KeyError(service.full_name)
        return ServiceClient(app, service)

    async def http(
        self,
        method: str,
        path: str,
        *,
        query: str = "",
        body: bytes = b"",
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        normalized = method.upper()
        handler = self._http.get((normalized, path))
        if handler is None:
            handler = self._http.get((normalized, "*"))
        if handler is None:
            if path in self._paths:
                return HttpResponse(status=405)
            return HttpResponse(status=404)
        request = HttpRequest(
            method=normalized,
            path=path,
            query=query,
            headers=headers or {},
            body=body,
        )
        return await handler(request)

    async def close(self) -> None:
        """Close every closeable once, in reverse order of registration."""
        if self._closed:
            return
        self._closed = True
        for closeable in reversed(self._closeables):
            await closeable.close()
