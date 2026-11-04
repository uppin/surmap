# Greppable agent server logs

**Date:** 2026-11-04
**Feature:** Survey agent / operations

- **Event log.** `surmap.agent.event_log`: logger `surmap.agent.events`, one
  `event=<name> key=value …` line for each turn start and end (reason, reply length, tool count,
  duration), tool call start and end (status, duration, error), sign-in (outcome only), refused
  call (surface, target) and station start, stop and idle stop.
- **Process.** `python -m surmap.agent` logs INFO to stderr with a timestamp, so
  `modal app logs surmap-agent | grep event=…` finds them in production.
- **Tests.** `tests/test_agent_event_log.py` (7).

Docs: [docs/agent.md](../../agent.md) (*Server logs*).
