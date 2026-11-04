# Changeset: Greppable agent server logs

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package, several seams (hub, routes, gate, station), log-capture tests

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery (PRD: operator-facing log lines, recorded here) · this file + discovery companion
- [wf 2] ⏳ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] `tests/test_agent_event_log.py` — the line format; turn, tool, error, sign-in, refusal and station lines
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `surmap.agent.event_log`: `log_event`, `logfmt`, `TurnLog`
  - [ ] Hooks: hub `_record`/`_record_user_message`; sign-in and refusals; station start/stop/idle
  - [ ] `python -m surmap.agent` sends INFO to stderr with a timestamp
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (V1; V4 grep on the deployed agent)
  - [ ] `docs/agent.md` — the log lines and how to grep them; changelog
  - [ ] Lint and quality gates green

## Initial Discovery

[initial-discovery.md](./2026-11-04-agent-event-logs-initial-discovery.md).

## Stack Context

On `agent-on-modal` (#123): the sign-in and refusal lines log #123's access gate.

### Inherited Dependencies — do not implement here

- The access gate and `/auth/session` (#123).

## Technical Changes

### State A (Current)

Access lines only.

### State B (Target)

Logger `surmap.agent.events`, INFO, one line per event: `event=<name>` then `key=value` pairs
(values with spaces or quotes are double-quoted). Lines:
`turn_started conversation turn model trigger=user|job` ·
`tool_started conversation turn tool call` ·
`tool_finished conversation turn tool call status=succeeded|failed|detached duration_ms [error]` ·
`turn_finished conversation turn reason text_chars tools duration_ms` ·
`turn_error conversation turn error` · `auth_signin result=ok|refused` (never the code) ·
`auth_refused surface=rpc|http target` · `station action=start|stop|idle_stop state duration_ms
[error]`. The process logs INFO to stderr as `<time> <level> <logger> <line>`.

## Verification

**Method:** V1-fail→pass — log-capture tests; V4 — grep the deployed agent's logs after a turn.
**Command:** `uv run pytest -q tests/test_agent_event_log.py`
**Before:** fails (no `surmap.agent.event_log`).
**After:** passes.
**Approved:** the developer, 2026-11-04 ("make sure there are server logs that can be grepped in production").
