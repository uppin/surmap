"""ConnectRPC over one WebSocket, with calls starting from either end.

A `SocketRpcPeer` owns one socket. It serves the connect-python applications it was given and
calls methods on the peer at the other end, every call multiplexed over the socket by stream id
(`surmap.transport.v1.SocketFrame`). The peer that dialed numbers its calls odd, the peer
that accepted numbers them even, so a server can call a method on an instance that dialed out.
"""

from surmap.rpc.socket_rpc._trace import describe_open_socket_calls
from surmap.rpc.socket_rpc._types import OpenCall
from surmap.rpc.socket_rpc.peer import (
    FrameSocket,
    PeerRole,
    SocketRpcError,
    SocketRpcPeer,
)
from surmap.rpc.socket_rpc.serve import ConnectWebSocketApp, connect_websocket_app
from surmap.rpc.socket_rpc.websocket import AsgiWebSocketFrames, WebSocketFrames

__all__ = [
    "AsgiWebSocketFrames",
    "ConnectWebSocketApp",
    "FrameSocket",
    "OpenCall",
    "PeerRole",
    "SocketRpcError",
    "SocketRpcPeer",
    "WebSocketFrames",
    "connect_websocket_app",
    "describe_open_socket_calls",
]
