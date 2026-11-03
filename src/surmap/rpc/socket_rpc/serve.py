"""Serve Connect applications over an accepted ASGI WebSocket, one acceptor peer per socket."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from connectrpc.server import ConnectASGIApplication

from surmap.rpc.socket_rpc.peer import PeerRole, SocketRpcPeer
from surmap.rpc.socket_rpc.websocket import AsgiWebSocketFrames

__all__ = ["connect_websocket_app"]


# An empty socket frame carries no request or response; peers skip it.
_KEEPALIVE_FRAME = b""


def connect_websocket_app(
    applications: Mapping[str, ConnectASGIApplication[Any]],
    *,
    keepalive_s: float | None = None,
) -> Callable[[dict[str, Any], Any, Any], Awaitable[None]]:
    """An ASGI WebSocket app: accept, then answer the dialer's calls on `applications` (keyed by
    fully-qualified service name) until the socket closes. The first frame it sends is empty —
    the dialer's sign that the socket is open for calls — and so is one every `keepalive_s`,
    so a proxy that drops connections idle on the server side keeps this one."""

    async def keep_alive(send: Any, interval_s: float) -> None:
        while True:
            await asyncio.sleep(interval_s)
            await send({"type": "websocket.send", "bytes": _KEEPALIVE_FRAME})

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        message = await receive()
        if message["type"] != "websocket.connect":
            return
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.send", "bytes": _KEEPALIVE_FRAME})
        peer = SocketRpcPeer(
            AsgiWebSocketFrames(receive, send), role=PeerRole.ACCEPTOR, applications=applications
        )
        pinging = (
            asyncio.create_task(keep_alive(send, keepalive_s)) if keepalive_s is not None else None
        )
        try:
            await peer.serve()
        finally:
            if pinging is not None:
                pinging.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pinging
            await peer.close()

    return app
