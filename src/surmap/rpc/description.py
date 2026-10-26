"""What a server is: its services, routes and closeables — static in shape, lazy in dependencies."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from google.protobuf.descriptor import ServiceDescriptor

from surmap.rpc.compose import Brick
from surmap.rpc.http import HttpHandler

__all__ = ["Closeable", "HttpRoute", "ServerDescription", "ServiceModule", "WebSocketRoute"]

C = TypeVar("C")


class Closeable(Protocol):
    async def close(self) -> None: ...


@dataclass(frozen=True)
class ServiceModule(Generic[C]):
    """One service, built from bricks only when a host mounts it."""

    descriptor: ServiceDescriptor
    bricks: Callable[[C], Sequence[Brick]]


@dataclass(frozen=True)
class HttpRoute(Generic[C]):
    """`method` + exact `path` → a handler built from the context when mounted."""

    method: str
    path: str
    handler: Callable[[C], HttpHandler]


@dataclass(frozen=True)
class WebSocketRoute(Generic[C]):
    path: str
    handler: Callable[[C], Callable[[Any], Awaitable[None]]]


@dataclass(frozen=True)
class ServerDescription(Generic[C]):
    services: Sequence[ServiceModule[C]] = field(default_factory=tuple)
    http_routes: Sequence[HttpRoute[C]] = field(default_factory=tuple)
    websocket_routes: Sequence[WebSocketRoute[C]] = field(default_factory=tuple)
    closeables: Callable[[C], Sequence[Closeable]] = field(default=lambda _context: ())
