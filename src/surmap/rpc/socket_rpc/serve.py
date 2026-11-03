"""Serve Connect applications over an accepted ASGI WebSocket, one acceptor peer per socket."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Mapping
from typing import Any

from connectrpc.server import ConnectASGIApplication

from surmap.rpc.socket_rpc._trace import socket_debug, socket_trace
from surmap.rpc.socket_rpc.peer import PeerRole, SocketRpcPeer
from surmap.rpc.socket_rpc.websocket import AsgiWebSocketFrames

__all__ = ["ConnectWebSocketApp", "connect_websocket_app"]


# An empty socket frame carries no request or response; peers skip it.
_KEEPALIVE_FRAME = b""


class ConnectWebSocketApp:
    """An ASGI WebSocket app: accept, then answer the dialer's calls on `applications` (keyed by
    fully-qualified service name) until the socket closes. The first frame it sends is empty —
    the dialer's sign that the socket is open for calls — and so is one every `keepalive_s`,
    so a proxy that drops connections idle on the server side keeps this one. `close_all`
    closes every socket it holds, so a stopping host does not wait on its clients to leave."""

    def __init__(
        self,
        applications: Mapping[str, ConnectASGIApplication[Any]],
        *,
        keepalive_s: float | None = None,
    ) -> None:
        self._applications = applications
        self._keepalive_s = keepalive_s
        self._peers: set[SocketRpcPeer] = set()

    async def close_all(self) -> None:
        """Close every socket this app holds open; each peer's open calls fail as cancelled."""
        for peer in list(self._peers):
            with contextlib.suppress(Exception):
                await peer.close()

    @staticmethod
    async def _keep_alive(send: Any, interval_s: float, client: str) -> None:
        while True:
            await asyncio.sleep(interval_s)
            await send({"type": "websocket.send", "bytes": _KEEPALIVE_FRAME})
            socket_debug("ws.server.keepalive", client=client)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        message = await receive()
        if message["type"] != "websocket.connect":
            return
        client = _client_of(scope)
        opened = time.monotonic()
        await send({"type": "websocket.accept"})
        socket_trace("ws.server.accepted", client=client, path=scope.get("path", ""))
        await send({"type": "websocket.send", "bytes": _KEEPALIVE_FRAME})
        socket_trace("ws.server.greeted", client=client)
        peer = SocketRpcPeer(
            AsgiWebSocketFrames(receive, send),
            role=PeerRole.ACCEPTOR,
            applications=self._applications,
        )
        self._peers.add(peer)
        pinging = (
            asyncio.create_task(self._keep_alive(send, self._keepalive_s, client))
            if self._keepalive_s is not None
            else None
        )
        try:
            await peer.serve()
        finally:
            self._peers.discard(peer)
            if pinging is not None:
                pinging.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pinging
            still_open = [f"{c.direction}:{c.method}" for c in peer.open_calls()]
            await peer.close()
            socket_trace(
                "ws.server.closed",
                client=client,
                duration_s=round(time.monotonic() - opened, 3),
                open_calls=still_open,
            )


def connect_websocket_app(
    applications: Mapping[str, ConnectASGIApplication[Any]],
    *,
    keepalive_s: float | None = None,
) -> ConnectWebSocketApp:
    """The Connect WebSocket app serving `applications` (see `ConnectWebSocketApp`)."""
    return ConnectWebSocketApp(applications, keepalive_s=keepalive_s)


def _client_of(scope: dict[str, Any]) -> str:
    client = scope.get("client")
    return f"{client[0]}:{client[1]}" if client else "?"
