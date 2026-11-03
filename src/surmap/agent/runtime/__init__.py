"""The survey agent's runtime: a LangGraph turn loop whose every tool call is a job.

- `jobs` — `JobRunner` owns each tool call as an asyncio task with an execution policy: sync
  (wait up to a timeout, then fail or detach), async (a job handle at once), steer-detach, cancel,
  and the notices finished background jobs feed back into the conversation.
- `graph` — the per-turn `model → tools → model …` graph with its round and repeated-failure caps.
- `tools` — binds a `ToolContract` and its handler to the runner; the built-in job tools.
- `session` — `AgentSession`: one conversation's turns, steering, cancel and idle job notices.
- `events` — the domain events a turn yields, which the chat server maps onto `TurnEvent`.
"""
