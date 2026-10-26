"""A `ServerDescription` on hypercorn: h1/h2 on a public port, routes on a management port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from connectrpc.server import ConnectASGIApplication

from surmap.rpc._listener import _HypercornServer, start_hypercorn
from surmap.rpc.compose import compose_service
from surmap.rpc.description import ServerDescription
from surmap.rpc.http import HttpHandler

__all__ = ["BoundPorts", "HypercornHost"]

C = TypeVar("C")


@dataclass(frozen=True)
class BoundPorts:
    public: int
    management: int | None


@dataclass
class _Mounted(Generic[C]):
    connect_apps: dict[str, ConnectASGIApplication[Any]]
    public_http: dict[tuple[str, str], HttpHandler]
    public_websockets: dict[str, Any]
    management_http: dict[tuple[str, str], HttpHandler]
    closeables: list[Any]


class HypercornHost(Generic[C]):
    def __init__(
        self,
        description: ServerDescription[C],
        context: C,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        management_port: int | None = None,
    ) -> None:
        self._description = description
        self._context = context
        self._host = host
        self._port = port
        self._management_port = management_port
        self._public_server: _HypercornServer | None = None
        self._management_server: _HypercornServer | None = None
        self._mounted: _Mounted[C] | None = None

    def _mount(self) -> _Mounted[C]:
        apps: dict[str, ConnectASGIApplication[Any]] = {}
        connect_paths: dict[str, ConnectASGIApplication[Any]] = {}
        for module in self._description.services:
            bricks = list(module.bricks(self._context))
            app = compose_service(module.descriptor, *bricks)
            apps[module.descriptor.full_name] = app
            for method in module.descriptor.methods:
                connect_paths[f"/{module.descriptor.full_name}/{method.name}"] = app

        http_handlers = {
            (route.method.upper(), route.path): route.handler(self._context)
            for route in self._description.http_routes
        }
        websocket_handlers = {
            route.path: route.handler(self._context) for route in self._description.websocket_routes
        }
        if self._management_port is not None:
            public_http: dict[tuple[str, str], HttpHandler] = {}
            public_websockets = websocket_handlers
            management_http = http_handlers
        else:
            public_http = http_handlers
            public_websockets = websocket_handlers
            management_http = {}

        closeables = list(self._description.closeables(self._context))
        return _Mounted(
            connect_apps=connect_paths,
            public_http=public_http,
            public_websockets=public_websockets,
            management_http=management_http,
            closeables=closeables,
        )

    async def start(self) -> BoundPorts:
        mounted = self._mount()
        self._mounted = mounted
        public_server, public_port = await start_hypercorn(
            host=self._host,
            port=self._port,
            connect_apps=mounted.connect_apps,
            http_handlers=mounted.public_http,
            websocket_handlers=mounted.public_websockets,
        )
        self._public_server = public_server
        management_port: int | None = None
        if self._management_port is not None:
            management_server, management_port = await start_hypercorn(
                host=self._host,
                port=self._management_port,
                connect_apps={},
                http_handlers=mounted.management_http,
            )
            self._management_server = management_server
        return BoundPorts(public=public_port, management=management_port)

    async def stop(self) -> None:
        if self._public_server is not None:
            self._public_server.close()
            await self._public_server.wait_closed()
            self._public_server = None
        if self._management_server is not None:
            self._management_server.close()
            await self._management_server.wait_closed()
            self._management_server = None
        if self._mounted is not None:
            for closeable in reversed(self._mounted.closeables):
                await closeable.close()
            self._mounted = None
