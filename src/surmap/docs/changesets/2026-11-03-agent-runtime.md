# Survey agent runtime (`surmap.agent.runtime`)

**Date:** 2026-11-03
**Type:** Feature
**Packages:** surmap

New `surmap.agent.runtime` package: `JobRunner` runs every tool call as an asyncio task under its
`ExecutionPolicy` (SYNC with FAIL or DETACH after the timeout, or ASYNC), queues a `JobNotice` when
a detached or async job ends, detaches waiting calls on a steer, and cancels a SYNC call whose
caller is cancelled mid-wait. `build_turn_graph` compiles the per-turn LangGraph `StateGraph`
(model, tools, `cut_off`, no checkpointer) with `TurnCaps` (30 rounds, `SURMAP_AGENT_MAX_ROUNDS`;
3 identical failures). `AgentSession` runs one turn at a time over a `ConversationStore`, with
`run_turn`, `steer`, `cancel` and `idle_events`; `bind_contract_tool` and `job_tools` bind
`ToolContract`s and the `AgentJobs` tools. Adds `langgraph>=1.2,<2` and `langchain-core>=1.6,<2`.

Tests: 43 in `tests/test_agent_runtime.py`, `tests/test_agent_jobs.py` and
`tests/test_agent_steering.py`, driven by `ScriptedChatModel` and `FakeToolHandler` in
`tests/agent_fakes.py` (no sleeps: held handlers are released by events). Full suite 1442 passed,
30 skipped; ruff, ruff format and strict mypy clean.
