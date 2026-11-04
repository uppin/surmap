# 2026-11-03 — SAM device, model and route flags on `python -m surmap.agent`

**Category:** Deferred scope
**Source:** `docs/surmap/1-WIP/2026-11-03-agent-chat-server.md` (PR #84, stack `#survey-agent` node 8/9)
**Packages:** surmap
**Consent:** Supervisor decision for the n8 wrap (2026-11-03): "`--sam-fake`-only: accepted for this PR. Record a TODO ... for SAM device/model/route flags on `python -m surmap.agent` mirroring `scripts/demo.py`"
**Status:** Open

## What is left

The station route is done: `--station modal|stub` runs the agent's SAM on a station (2026-11-04,
`docs/agent.md` *SAM station*). Still missing is a **local** real SAM: `scripts/demo.py`'s
`--sam-model <id|path>` and device, carried into `AgentServerConfig` and the demo run host, with a
real-SAM config test in `tests/test_agent_server_app.py`. The process now refuses to start with
neither `--station` nor `--sam-fake`.

## Why it could not be done now

The flags reuse `scripts/demo.py`'s SAM wiring, which the stack has not lifted into a shared module;
copying it into this node would fork the wiring, and the sweep node owns cross-node consolidation.
The fake SAM is enough for every acceptance test and for the chat UI (n9).

## History

| Date | Event |
|---|---|
| 2026-11-03 | Recorded at the n8 wrap (#84); assigned to the `#survey-agent` sweep node |
| 2026-11-04 | Narrowed: the station route landed with the agent station lifecycle (#113); local model and device remain |
