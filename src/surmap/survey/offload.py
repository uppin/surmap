"""Blocking backend work, run off the event loop, one call at a time per backend.

The CM5 serves every call of a client on one event loop, so SLAM, stereo and object-point work
runs in threads. Several streams can share one backend (the CM5's default SLAM, its object-point
source), and a backend was never called concurrently while that work ran on the loop; each
backend's calls are serialized here to keep it so.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import ParamSpec, TypeVar

__all__ = ["forget_backend", "run_blocking"]

P = ParamSpec("P")
T = TypeVar("T")

_GUARDS: dict[int, threading.Lock] = {}
_GUARDS_LOCK = threading.Lock()


def _guard(backend: object) -> threading.Lock:
    with _GUARDS_LOCK:
        return _GUARDS.setdefault(id(backend), threading.Lock())


async def run_blocking(
    backend: object, call: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    """`call(*args, **kwargs)` in a worker thread, holding `backend`'s lock."""
    guard = _guard(backend)

    def locked() -> T:
        with guard:
            return call(*args, **kwargs)

    return await asyncio.to_thread(locked)


def forget_backend(backend: object) -> None:
    """Drop `backend`'s lock once nothing calls it any more (a closed per-stream backend)."""
    with _GUARDS_LOCK:
        _GUARDS.pop(id(backend), None)
