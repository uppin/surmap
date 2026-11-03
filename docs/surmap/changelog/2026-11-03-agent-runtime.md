# Survey agent runtime — LangGraph loop, job runner, steering

**Date:** 2026-11-03
**Feature:** Survey agent

The survey agent gained its loop. A turn is a LangGraph graph — `model → tools → model …` — with a
round cap (30, `SURMAP_AGENT_MAX_ROUNDS`) and a cap of three identical failing calls, both routed
to a `cut_off` node that answers the remaining calls "Not run". Every tool call runs as a job under
its execution policy: a `SYNC` call returns inline within its timeout and then either fails
(`FAIL`, the job cancelled) or detaches to a job handle (`DETACH`); an `ASYNC` call returns a
handle at once. Detached and async jobs report back as notices the model reads before its next
call, or, while the conversation is idle, through `AgentSession.idle_events()`. A person can steer
a running turn: the steer is queued for the model's next call and every blocking call detaches
(never cancels) so the model reads it at once; steering an idle conversation starts a turn. Cancel
ends the turn and its running jobs and keeps the completed rounds. Turns stream domain events
(`TextDelta`, `ToolCallStarted`, `ToolCallFinished`, `JobUpdate`, `SteerApplied`, `TurnFinished`,
`TurnError`) for the chat server to map. No caller yet: the model providers and SurMap tools plug
in next.

Behaviour is described in [docs/agent.md](../../agent.md#runtime-surmapagentruntime).
