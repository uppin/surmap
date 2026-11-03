# private-reach: src/surmap/agent/tools/workspace.py — `DemoWorkspace._start`

**Location:** `src/surmap/agent/tools/workspace.py` — `DemoWorkspace._start`
**Category:** private-reach (judged; cross-module use of private `surmap.demo.runs` symbols)
**Detected:** 2026-11-03 by `/pr-wrap` (#83, `#survey-agent` 7/9) review of the green step
**Metrics:** 2 private symbols reached (`DemoRunHost._take_over`, `_RunEngine`) · one `dict[str, Any]` options bag at the boundary
**Restructure:** not required — a public parameter on `DemoRunHost.start_run`, ordinary work
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)

## Measurement history

| Run | Private symbols | Note |
|---|---|---|
| 2026-11-03 | 2 | #83 (`#survey-agent` 7/9) added it; `src/surmap/demo/runs.py` belongs to n2 (#77 lineage), so it is not edited here. Assigned to the `#survey-agent` sweep node (n9) |

## What the tool found

`DemoRunHost.start_run` reads only the host-wide `player_options`, so a per-call `fps` and
`max_frames` cannot be passed. `DemoWorkspace._start` therefore builds the run itself: it overlays
the call's values on `player_options`, constructs `_RunEngine` and calls `_take_over` — both private
to `surmap.demo.runs`.

## Why it matters here

Any change to the host's takeover or engine construction (locking, registration, cleanup) silently
diverges between `start_run` and this copy; nothing in `demo/runs.py` knows the agent depends on
its internals.

## What would close it

Give `DemoRunHost.start_run` a public per-call options parameter, e.g.
`start_run(prepared, sam_prompt, *, player_options: PlayerOptions | None = None)` with a typed
`PlayerOptions` (`fps`, `max_frames`) overlaid on the host's options for that run only; then
`DemoWorkspace._start` calls it and the `_take_over` / `_RunEngine` imports go. Lands in the sweep
node of `#survey-agent`, which may edit n2's file.

## Verified by hand

2026-11-03: `grep -n "_take_over\|_RunEngine" src/surmap/agent` — the only reach is
`DemoWorkspace._start` (import in `workspace.py`). `start_run` in `src/surmap/demo/runs.py` takes no
per-call options. Tests cover the path (`tests/test_agent_tools_demo.py`, `max_frames` and cancel
tests).
