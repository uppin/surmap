"""Optional socket-RPC diagnostics, enabled by environment variables."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

_TRACE_ENV = "SURMAP_SOCKET_RPC_TRACE"
_DEBUG_ENV = "SURMAP_SOCKET_RPC_DEBUG"
_TEST_TRACE_ENV = "SURMAP_SOCKET_RPC_TEST_TRACE"
_LOGGER = logging.getLogger("surmap.rpc.socket_rpc.trace")
_T0 = time.monotonic()
_SEQ = 0


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
