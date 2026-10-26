"""Minimal hypercorn listener for kit hosts — Connect RPC paths and plain HTTP routes."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from connectrpc.server import ConnectASGIApplication

from surmap.rpc.http import HttpHandler, HttpRequest, HttpResponse
from surmap.rpc.http_limits import (
    ClientDisconnected,
    RequestBodyTooLargeError,
    read_limited_body,
)

AsgiApp = Callable[..., Awaitable[None]]
WebSocketAsgiApp = Callable[..., Awaitable[None]]


def _looks_like_rpc(path: str) -> bool:
    segments = path.strip("/").split("/")
    return len(segments) == 2 and "." in segments[0]


async def _send_response(send: Any, response: HttpResponse) -> None:
    headers = [(k.lower().encode(), v.encode()) for k, v in response.headers.items()]
    await send({"type": "http.response.start", "status": response.status, "headers": headers})
    await send({"type": "http.response.body", "body": response.body, "more_body": False})


async def _send_plain(send: Any, *, status: int, body: bytes, headers: Mapping[str, str]) -> None:
    await _send_response(send, HttpResponse(status=status, body=body, headers=dict(headers)))


def build_listener_app(
    *,
    connect_apps: Mapping[str, ConnectASGIApplication[Any]],
    http_handlers: Mapping[tuple[str, str], HttpHandler],
    websocket_handlers: Mapping[str, WebSocketAsgiApp] | None = None,
) -> AsgiApp:
    paths_by_method: dict[str, set[str]] = {}
    for method, path in http_handlers:
        paths_by_method.setdefault(path, set()).add(method)
    websockets = websocket_handlers or {}

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        scope_type = scope["type"]
        if scope_type == "websocket":
            path = scope.get("path", "")
            ws_app = websockets.get(path)
            if ws_app is None:
                await send({"type": "websocket.close", "code": 1008})
                return
            await ws_app(scope, receive, send)
            return

        if scope_type != "http":
            return
        method = scope["method"]
        path = scope["path"]
        query = scope.get("query_string", b"").decode()
        header_pairs = scope.get("headers", ())
        headers = {name.decode().lower(): value.decode() for name, value in header_pairs}

        if method == "POST" and _looks_like_rpc(path):
            connect_app = connect_apps.get(path)
            if connect_app is None:
                await _send_plain(send, status=404, body=b"", headers={})
                return
            await connect_app(scope, receive, send)
            return

        handler = http_handlers.get((method, path))
        if handler is None:
            handler = http_handlers.get((method, "*"))
        if handler is None:
            if path in paths_by_method:
                await _send_plain(send, status=405, body=b"", headers={})
            else:
                await _send_plain(send, status=404, body=b"", headers={})
            return

        try:
            body = await read_limited_body(receive)
        except RequestBodyTooLargeError:
            await _send_plain(send, status=413, body=b"", headers={})
            return
        except ClientDisconnected:
            return

        request = HttpRequest(method=method, path=path, query=query, headers=headers, body=body)
        response = await handler(request)
        await _send_response(send, response)

    return app


@dataclass
class _HypercornServer:
    _shutdown: asyncio.Event
    _task: asyncio.Task[None]
    _bind_socket: socket.socket | None = None

    def close(self) -> None:
        self._shutdown.set()

    async def wait_closed(self) -> None:
        await self._task
        # Hypercorn owns the fd passed via `fd://`; do not close it again here.
        self._bind_socket = None


async def start_hypercorn(
    *,
    host: str,
    port: int,
    connect_apps: Mapping[str, ConnectASGIApplication[Any]],
    http_handlers: Mapping[tuple[str, str], HttpHandler],
    websocket_handlers: Mapping[str, WebSocketAsgiApp] | None = None,
    app: AsgiApp | None = None,
) -> tuple[_HypercornServer, int]:
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    if app is None:
        app = build_listener_app(
            connect_apps=connect_apps,
            http_handlers=http_handlers,
            websocket_handlers=websocket_handlers,
        )
    bind_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bind_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bind_socket.bind((host, port))
    bound_port = bind_socket.getsockname()[1]
    bind_socket.setblocking(False)
    try:
        bind_socket.set_inheritable(True)
    except AttributeError:
        pass

    config = Config()
    config.bind = [f"fd://{bind_socket.fileno()}"]
    shutdown = asyncio.Event()

    async def _run() -> None:
        await serve(app, config, shutdown_trigger=shutdown.wait)

    task = asyncio.create_task(_run())
    await _await_ready(host=host, port=bound_port, task=task)
    return _HypercornServer(shutdown, task, bind_socket), bound_port


async def _await_ready(*, host: str, port: int, task: asyncio.Task[None]) -> None:
    deadline = asyncio.get_running_loop().time() + 5.0
    while True:
        if task.done():
            exc = task.exception()
            if exc is not None:
                raise exc
            raise RuntimeError("hypercorn exited before accepting connections")
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=0.2
            )
            writer.close()
            await writer.wait_closed()
            return
        except (OSError, TimeoutError):
            pass
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"hypercorn did not listen on {host}:{port}")
        await asyncio.sleep(0.02)
