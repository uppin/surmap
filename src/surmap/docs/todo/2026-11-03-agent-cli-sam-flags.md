# 2026-11-03 — SAM device, model and route flags on `python -m surmap.agent`

**Category:** Deferred scope
**Source:** `docs/surmap/1-WIP/2026-11-03-agent-chat-server.md` (PR #84, stack `#survey-agent` node 8/9)
**Packages:** surmap
**Consent:** Supervisor decision for the n8 wrap (2026-11-03): "`--sam-fake`-only: accepted for this PR. Record a TODO ... for SAM device/model/route flags on `python -m surmap.agent` mirroring `scripts/demo.py`"
**Status:** Open

## What is left

`build_demo_workspace` (`src/surmap/agent/server/app.py`) refuses to start without `--sam-fake`
(`ValueError: the agent process runs the fake SAM only for now`). The agent CLI
(`src/surmap/agent/__main__.py`) needs the SAM flags `scripts/demo.py` has — `--sam-model <id|path>`,
the device, and the station route (`--station-host`) — carried into `AgentServerConfig` and the demo
run host, so the agent runs a real detector. Then drop the refusal and cover a real-SAM config in
`tests/test_agent_server_app.py`.

## Why it could not be done now

The flags reuse `scripts/demo.py`'s SAM wiring, which the stack has not lifted into a shared module;
copying it into this node would fork the wiring, and the sweep node owns cross-node consolidation.
The fake SAM is enough for every acceptance test and for the chat UI (n9).

## History

| Date | Event |
|---|---|
| 2026-11-03 | Recorded at the n8 wrap (#84); assigned to the `#survey-agent` sweep node |
