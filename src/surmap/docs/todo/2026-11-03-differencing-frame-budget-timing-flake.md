# 2026-11-03 — The differencing frame-budget test fails under CPU load

**Category:** Known failing test
**Source:** PR #101, stack `#sim-disaster-2` n4 (2 of 4), Wrap row — the intermittent full-suite failure seen in review round 1
**Packages:** surmap
**Consent:** n/a — pre-existing, outside this change (reason below)
**Status:** Open

## What is left

`tests/test_moving_differencing.py::test_differencing_is_within_frame_budget` asserts a
wall-clock bound — one `StaticLayer.difference` over 4000 points in under 0.05 s
(`time.perf_counter`). On a loaded host it fails intermittently: in this wrap it failed once in
a full `uv run pytest -q` run that overlapped a `cargo clippy` build (it was the only failure),
4 of 6 isolated runs during that build (0.21–1.52 s), and 2 of 6 runs of the same test on
n3's untouched head `f0cf358` under synthetic CPU load (0.21 s, 0.29 s). On an idle host it
passes: the wrap's next four full runs (three `pytest -q`, one `pytest -x -q`) were all green. The wrap's
last full run, with other sessions holding the host at a load average of about 50, failed on
this test alone (1886 passed), and it failed 4 of 4 isolated reruns at that load.
Wanted: a budget check that does not depend on what else the machine runs — for example the
minimum of several timed runs, a CPU-time clock (`time.process_time`), or a benchmark marker
kept out of the default gate — still catching a real regression of the differencing cost.

## Why it could not be done now

The test and `surmap/moving/differencing.py` are identical on this branch and on its base (it
dates from PR #21, `#moving-objects` 3/6); nothing in the behaviour-tree change touches them.
Changing how a performance budget is measured is that package's decision, and doing it here
would put an unrelated test change into a reviewed simulation PR.

## What was done instead

Nothing in code.

## When it becomes possible

Now — any PR on `surmap/moving` (or the stack's sweep node) can take it.
