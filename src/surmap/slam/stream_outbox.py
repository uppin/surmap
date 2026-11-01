"""What the streaming backend sends the sidecar, and the region answers it waits for.

`SidecarOutbox` is the writer thread's input: two lanes behind one
condition. Control requests (region queries) go out first and are never
dropped; pairs drop oldest when RTAB-Map falls behind, and a closing
sentinel ends the stream once the pairs queued before it are written.

`RegionReplies` matches each `region` line the reader decodes to the
caller waiting on that `query_id`, so concurrent queries never see each
other's answers whatever order the sidecar replies in.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Generic, TypeVar

from surmap.slam.regions import RegionResult

Pair = TypeVar("Pair")


class SidecarOutbox(Generic[Pair]):
    """Two-lane, thread-safe queue in front of the sidecar's stdin."""

    def __init__(self, queue_size: int) -> None:
        self._ready = threading.Condition()
        self._controls: deque[bytes] = deque()
        self._pairs: deque[Pair | None] = deque()
        self._queue_size = max(1, queue_size)
        self._dropped = 0

    @property
    def dropped(self) -> int:
        """Pairs dropped so far because RTAB-Map fell behind."""
        with self._ready:
            return self._dropped

    def put_pair(self, pair: Pair) -> None:
        with self._ready:
            if len(self._pairs) >= self._queue_size and self._pairs[0] is not None:
                self._pairs.popleft()
                self._dropped += 1
            self._pairs.append(pair)
            self._ready.notify()

    def put_control(self, data: bytes) -> None:
        with self._ready:
            self._controls.append(data)
            self._ready.notify()

    def close(self) -> None:
        """End the stream after the pairs already queued."""
        with self._ready:
            self._pairs.append(None)
            self._ready.notify()

    def take(self) -> bytes | Pair | None:
        """The next control request, else the next pair; None once closed."""
        with self._ready:
            while not self._controls and not self._pairs:
                self._ready.wait()
            if self._controls:
                return self._controls.popleft()
            return self._pairs.popleft()


class RegionReplies:
    """Region answers by `query_id`, handed from the reader to each waiting caller."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._waiting: dict[int, tuple[threading.Event, list[RegionResult]]] = {}

    def expect(self, query_id: int) -> None:
        with self._lock:
            self._waiting[query_id] = (threading.Event(), [])

    def deliver(self, result: RegionResult) -> None:
        with self._lock:
            waiter = self._waiting.get(result.query_id)
        if waiter is not None:
            waiter[1].append(result)
            waiter[0].set()

    def wait(self, query_id: int, timeout: float) -> RegionResult | None:
        """That query's answer, or None if none arrived in time; forgets the query."""
        with self._lock:
            answered, slot = self._waiting[query_id]
        try:
            return slot[0] if answered.wait(timeout=timeout) else None
        finally:
            with self._lock:
                self._waiting.pop(query_id, None)
