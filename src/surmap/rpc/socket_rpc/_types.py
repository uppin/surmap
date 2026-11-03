"""Types both halves of a `SocketRpcPeer` share: the socket, the roles, the per-call state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, TypeVar

from connectrpc.code import Code
from connectrpc.compat import google_protobuf_codecs
from connectrpc.method import MethodInfo
from google.protobuf.message import Message

from surmap.transport.v1 import socket_rpc_pb2

REQ = TypeVar("REQ", bound=Message)
RES = TypeVar("RES", bound=Message)

_DEFAULT_CODEC = google_protobuf_codecs()[0]

# A body travels as frames of at most this many payload bytes, so no frame nears a WebSocket
# message limit (1 MiB by default) however large the body is.
DEFAULT_CHUNK_BYTES = 256 * 1024
# What a receiver buffers for one call before refusing it; a refused call fails alone.
DEFAULT_MAX_CALL_BYTES = 64 * 1024 * 1024


class FrameSocket(Protocol):
    """The socket a peer runs over: binary frames in, binary frames out."""

    async def send(self, frame: bytes) -> None: ...

    async def recv(self) -> bytes:
        """The next frame; raises when the socket has closed."""
        ...

    async def close(self) -> None: ...


class PeerRole(Enum):
    """Which end of the socket this peer is — it decides the parity of the stream ids it opens."""

    DIALER = "dialer"
    """Opened the socket; its calls use odd stream ids."""

    ACCEPTOR = "acceptor"
    """Accepted the socket; its calls use even stream ids."""


class SocketRpcError(Exception):
    """A call failed: the called peer's Connect error, or a transport failure."""

    def __init__(self, code: Code, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class _IncomingCall:
    stream_id: int
    init: socket_rpc_pb2.CallInit
    request_chunks: list[bytes] = field(default_factory=list)
    buffered_bytes: int = 0
    ended: bool = False
    aborted: bool = False
    task: asyncio.Task[None] | None = None
    request_more: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class _OutgoingCall:
    stream_id: int
    method: MethodInfo[Any, Any]
    kind: str
    response_queue: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    error: SocketRpcError | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    response_body: bytearray = field(default_factory=bytearray)
    buffer_body: bool = True
    headers_sent: bool = False
    finished: bool = False
