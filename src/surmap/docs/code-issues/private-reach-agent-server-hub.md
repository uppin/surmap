# private-reach: src/surmap/agent/server/hub.py — `_session_running`

**Location:** `src/surmap/agent/server/hub.py` — `_session_running`
**Category:** private-reach (judged; cross-module read of `AgentSession._active`)
**Detected:** 2026-11-03 by `/green` (#84, `#survey-agent` 8/9), recorded at the wrap
**Metrics:** 1 private attribute reached (`AgentSession._active`)
**Restructure:** not required — a public read-only property on `AgentSession`
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)

## Measurement history

| Run | Private symbols | Note |
|---|---|---|
| 2026-11-03 | 1 | #84 (`#survey-agent` 8/9) added it; `AgentSession` lives in n4's `surmap.agent.runtime` module, so it is not edited here. Assigned to the `#survey-agent` sweep node |

## What the tool found

`ChatHub` decides "busy" (a second `StreamTurn`) and whether a `Steer` is accepted by reading
`session._active`, the flag `AgentSession.run_turn` checks itself.

## What would close it

Add a public `AgentSession.is_running` (read-only property over `_active`) in n4's runtime module,
and have `_session_running` in `hub.py` use it.

## Verified by hand

2026-11-03: `grep -n "_active" src/surmap/agent/server` — the only reach is `hub.py:213`.
