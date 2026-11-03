"""Suite-wide pytest hooks: a hang dump for any test that runs past its budget.

`SURMAP_TEST_HANG_DUMP_S` sets the budget in seconds (default 120; 0 turns it off). See
`tests/hang_dump.py` for what the dump holds.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Generator

import pytest

from tests.hang_dump import DEFAULT_BUDGET_S, HangWatchdog


def _budget_s() -> float:
    raw = os.environ.get("SURMAP_TEST_HANG_DUMP_S", "").strip()
    return float(raw) if raw else DEFAULT_BUDGET_S


def _uncaptured_writer(config: pytest.Config) -> Callable[[str], None]:
    """Writes to the terminal past pytest's capture, which holds fd 2 while a test runs."""
    capture = config.pluginmanager.getplugin("capturemanager")

    def write(text: str) -> None:
        if capture is None:
            if sys.__stderr__ is not None:
                sys.__stderr__.write(text)
                sys.__stderr__.flush()
            return
        with capture.global_and_fixture_disabled():
            sys.stderr.write(text)
            sys.stderr.flush()

    return write


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item) -> Generator[None, None, None]:
    budget = _budget_s()
    if budget <= 0:
        yield
        return
    watchdog = HangWatchdog(budget, write=_uncaptured_writer(item.config))
    watchdog.start(item.nodeid)
    try:
        yield
    finally:
        watchdog.stop()
