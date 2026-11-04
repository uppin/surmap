"""The test suite's hang dump: what a test stuck past its budget prints to the CI log.

`tests/hang_dump.py` is armed for every test by `tests/conftest.py`; when one runs longer than
`SURMAP_TEST_HANG_DUMP_S` (default 120 s) it writes every thread's stack, every pending asyncio
task and the open socket-RPC calls to stderr, which reaches the CI log even while pytest captures.
"""

from __future__ import annotations

import asyncio
import io
import weakref

from tests.hang_dump import HangWatchdog, hang_report


async def test_the_report_names_the_pending_task_and_where_it_waits() -> None:
    # Given a task stuck on an event nobody sets
    stuck = asyncio.Event()

    async def waiting_for_the_socket() -> None:
        await stuck.wait()

    task = asyncio.create_task(waiting_for_the_socket(), name="survey-reader")
    await asyncio.sleep(0)

    # When the hang report is written
    report = hang_report("tests/test_x.py::test_stuck", elapsed_s=121.0)
    task.cancel()

    # Then it names the test, the task and the coroutine it is suspended in
    assert "tests/test_x.py::test_stuck" in report
    assert "survey-reader" in report
    assert "waiting_for_the_socket" in report
    assert "socket-RPC calls open" in report


def test_the_watchdog_writes_the_report_once_the_budget_is_exceeded() -> None:
    # Given a watchdog with a 0.1 s budget writing to a buffer
    out = io.StringIO()
    watchdog = HangWatchdog(budget_s=0.1, out=out)

    # When a test runs past it
    watchdog.start("tests/test_x.py::test_slow")
    finished = watchdog.wait_fired(timeout_s=2.0)
    watchdog.stop()

    # Then the report was written for that test
    assert finished
    assert "HANG DUMP" in out.getvalue() and "tests/test_x.py::test_slow" in out.getvalue()


def test_a_test_that_finishes_in_time_writes_nothing() -> None:
    # Given a watchdog with a 1 s budget
    out = io.StringIO()
    watchdog = HangWatchdog(budget_s=1.0, out=out)

    # When the test finishes well before it
    watchdog.start("tests/test_x.py::test_quick")
    watchdog.stop()

    # Then nothing was written
    assert out.getvalue() == ""


class Referent:
    """An object only a weak proxy will point at."""


def test_a_dead_weak_proxy_in_memory_does_not_cut_the_report_short() -> None:
    # Given a weak proxy still held after the object it points at is gone
    referent = Referent()
    held: list[object] = [weakref.proxy(referent)]
    del referent

    # When the hang report is written
    report = hang_report("tests/test_x.py::test_stuck", elapsed_s=121.0)

    # Then it is written to its end
    assert report.endswith("===== END HANG DUMP =====\n")
    assert len(held) == 1
