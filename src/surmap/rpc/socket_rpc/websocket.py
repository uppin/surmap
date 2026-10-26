"""`FrameSocket` adapters for websockets and ASGI WebSocket scopes."""

from __future__ import annotations

from typing import Any

import websockets

__all__ = ["AsgiWebSocketFrames", "WebSocketFrames"]


class WebSocketFrames:
    """Frames over a `websockets` client or server connection."""

    def __init__(
        self, websocket: websockets.ServerConnection | websockets.ClientConnection
    ) -> None:
        self._websocket = websocket

    async def send(self, frame: bytes) -> None:
        await self._websocket.send(frame)

    async def recv(self) -> bytes:
        raw = await self._websocket.recv()
        if isinstance(raw, str):
            return raw.encode()
        return raw

    async def close(self) -> None:
        await self._websocket.close()


class AsgiWebSocketFrames:
    """Frames over an accepted ASGI WebSocket (`receive` / `send`)."""

    def __init__(self, receive: Any, send: Any) -> None:
        self._receive = receive
        self._send = send

    async def send(self, frame: bytes) -> None:
        await self._send({"type": "websocket.send", "bytes": frame})

    async def recv(self) -> bytes:
        while True:
            message = await self._receive()
            if message["type"] == "websocket.receive":
                data: bytes | None = message.get("bytes")
                if data is not None:
                    return data
                text: str | None = message.get("text")
                if text is not None:
                    return text.encode()
            if message["type"] == "websocket.disconnect":
                raise ConnectionError("websocket disconnected")

    async def close(self) -> None:
        await self._send({"type": "websocket.close"})
