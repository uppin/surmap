"""A watchdog that, when a test runs past its budget, writes where everything is waiting.

A hang behind a WebSocket shows nothing on its own: the test sits in the event loop's select,
and CI only says the step is still running. The report names the test and lists every thread's
stack, every pending asyncio task with the coroutine frame it is suspended in, and the
socket-RPC calls every live peer still has open (`surmap.rpc.socket_rpc`). It is written to the
real stderr, so it reaches the CI log even while pytest captures output. It does not stop the
test; the CI job's timeout does.
"""

from __future__ import annotations

import asyncio
import gc
import sys
import threading
import time
import traceback
from collections.abc import Callable
from typing import TextIO

from surmap.rpc.socket_rpc import describe_open_socket_calls

DEFAULT_BUDGET_S = 120.0


def hang_report(nodeid: str, elapsed_s: float) -> str:
    """The report for `nodeid`, stuck for `elapsed_s`: threads, asyncio tasks, socket calls."""
    lines = [f"===== HANG DUMP: {nodeid} running {elapsed_s:.0f}s =====", ""]
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    for ident, frame in sys._current_frames().items():
        lines.append(f"--- thread {names.get(ident, ident)} ---")
        lines.extend(line.rstrip("\n") for line in traceback.format_stack(frame))
    lines.append("")
    tasks = _pending_tasks()
    lines.append(f"--- asyncio tasks pending: {len(tasks)} ---")
    for task in tasks:
        coro = task.get_coro()
        lines.append(f"task {task.get_name()} coro={getattr(coro, '__qualname__', coro)}")
        for frame in task.get_stack(limit=8):
            lines.append(
                f"    {frame.f_code.co_filename}:{frame.f_lineno} in {frame.f_code.co_name}"
            )
    calls = describe_open_socket_calls()
    lines.append("")
    lines.append(f"--- socket-RPC calls open: {len(calls)} ---")
    lines.extend(calls)
    lines.append("===== END HANG DUMP =====")
    return "\n".join(lines) + "\n"


def _pending_tasks() -> list[asyncio.Task[object]]:
    """Every unfinished task of every open event loop, read from any thread."""
    loops = [obj for obj in gc.get_objects() if _is_event_loop(obj)]
    tasks: list[asyncio.Task[object]] = []
    for loop in loops:
        if loop.is_closed():
            continue
        for _attempt in range(3):  # the loop's task set may change while it is read
            try:
                tasks.extend(task for task in asyncio.all_tasks(loop) if not task.done())
                break
            except RuntimeError:
                continue
    return tasks


def _is_event_loop(obj: object) -> bool:
    """Whether a live object is an event loop; a `weakref.proxy` whose referent is gone (a failed
    test's kept traceback can hold one) is not, rather than raising `ReferenceError`."""
    try:
        return isinstance(obj, asyncio.AbstractEventLoop)
    except ReferenceError:
        return False


class HangWatchdog:
    """Arms once per test; writes `hang_report` to `out` if the test outlives `budget_s`."""

    def __init__(
        self,
        budget_s: float = DEFAULT_BUDGET_S,
        out: TextIO | None = None,
        write: Callable[[str], None] | None = None,
    ) -> None:
        """The report goes to `write`, else to `out`, else to the real stderr. Under pytest's
        output capture `write` must bypass it (see `tests/conftest.py`), or the report of a test
        that never finishes is lost with the test's captured output."""
        self._budget_s = budget_s
        self._out = out
        self._write = write
        self._timer: threading.Timer | None = None
        self._fired = threading.Event()

    def start(self, nodeid: str) -> None:
        started = time.monotonic()
        self._fired.clear()

        def fire() -> None:
            report = hang_report(nodeid, time.monotonic() - started)
            if self._write is not None:
                self._write(report)
            else:
                out = self._out or sys.__stderr__
                if out is not None:
                    out.write(report)
                    out.flush()
            self._fired.set()

        self._timer = threading.Timer(self._budget_s, fire)
        self._timer.daemon = True
        self._timer.start()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def wait_fired(self, timeout_s: float) -> bool:
        return self._fired.wait(timeout_s)
