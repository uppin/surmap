"""Optional socket-RPC diagnostics, enabled by environment variables."""

from __future__ import annotations

import logging
import os
import time
import weakref
from typing import Any, Protocol

_TRACE_ENV = "SURMAP_SOCKET_RPC_TRACE"
_DEBUG_ENV = "SURMAP_SOCKET_RPC_DEBUG"
_TEST_TRACE_ENV = "SURMAP_SOCKET_RPC_TEST_TRACE"
_LOGGER = logging.getLogger("surmap.rpc.socket_rpc.trace")
_T0 = time.monotonic()
_SEQ = 0


class _Peer(Protocol):
    @property
    def role_name(self) -> str: ...

    def open_calls(self) -> list[Any]: ...


_PEERS: weakref.WeakSet[_Peer] = weakref.WeakSet()


def register_peer(peer: _Peer) -> None:
    """Make `peer` visible to `describe_open_socket_calls` for as long as it lives."""
    _PEERS.add(peer)


def describe_open_socket_calls() -> list[str]:
    """One line per call any live peer has open — what a hang is waiting on."""
    lines: list[str] = []
    for peer in list(_PEERS):
        for call in peer.open_calls():
            lines.append(
                f"{peer.role_name} {call.direction} stream={call.stream_id} {call.method} "
                f"open {call.age_s:.1f}s"
            )
    return lines


def _enabled() -> bool:
    for name in (_TRACE_ENV, _TEST_TRACE_ENV):
        if os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}:
            return True
    return False


def socket_debug_enabled() -> bool:
    return os.environ.get(_DEBUG_ENV, "").strip().lower() in {"1", "true", "yes"}


def socket_debug(event: str, **fields: Any) -> None:
    if not socket_debug_enabled():
        return
    parts = " ".join(f"{key}={value!r}" for key, value in sorted(fields.items()))
    _LOGGER.debug("%s %s", event, parts)


def socket_trace(event: str, **fields: Any) -> None:
    global _SEQ
    if not _enabled():
        return
    _SEQ += 1
    parts = " ".join(f"{key}={value!r}" for key, value in sorted(fields.items()))
    _LOGGER.info("+%.3fs #%s %s %s", time.monotonic() - _T0, _SEQ, event, parts)
