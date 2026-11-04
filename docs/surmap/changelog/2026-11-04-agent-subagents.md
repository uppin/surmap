# The survey agent delegates work to subagents it can steer

**Date:** 2026-11-04
**Feature:** Survey agent / subagents

- **Tools.** `start_subagent(task, name?, skill?)` hands one task to a subagent — its own
  `AgentSession`, `JobRunner` and history, on the conversation's model, with the conversation's
  tools minus the subagent tools plus `message_main_agent` — and returns `{subagent_id, name,
  job_id}`. Its system prompt is `SUBAGENT_PROMPT` and the named skill's body. `message_subagent`
  steers it while it runs, or starts a follow-up turn on its kept history once it has finished.
  At most 3 run at once per conversation.
- **Turns are jobs.** Each subagent turn is an ASYNC job (`subagent:sa-<n>`) of the main
  conversation, so `wait_for_jobs`, `cancel_job`, Stop and the jobs panel cover it; the result is
  `{subagent_id, name, finish_reason, reply}`. The subagent's tool calls never enter the main
  context.
- **Messages back.** `message_main_agent` queues a `SubagentNotice` beside job notices: read before
  the main agent's next model call (tagged `surmap_kind = subagent_message`), or opening a turn
  while it idles. New `TurnEvent.subagent_message {subagent_id, name, text}`; the chat UI shows it
  as a subagent card.
- **Simulation skills.** `creating-a-simulation` (main agent: brief, delegate, relay questions,
  report) and `building-a-simulation-scene` (the subagent's procedure over the simulation tools).
- **Code.** `surmap.agent.subagents`; `Notice` / `SubagentNotice` in `runtime/jobs.py`;
  `AgentSession.running`, `notice_event`, `notice_trigger`; `ChatHub(subagents=…)`;
  `contracts.tool_input_schema` (shared with the skill tools).
- **Tests.** `tests/test_agent_subagents.py`, `test_agent_subagent_messages.py`,
  `test_agent_subagent_skills.py` (20) over `tests/agent_subagent_fakes.py`; one mapping test in
  `test_agent_server_events.py`; web reducer and transcript tests.

Docs: [docs/agent.md](../../agent.md) § *Subagents*.
