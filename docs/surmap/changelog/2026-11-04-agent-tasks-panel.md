# Agent chat Tasks panel with subagent status

**Date:** 2026-11-04
**Feature:** Survey agent runtime and chat UI

- **Tasks panel.** The chat's Jobs panel was renamed Tasks ("No tasks yet"). It listed each
  subagent with its label, a *Subagent* tag, status, elapsed time and what it last reported;
  Cancel on a running subagent cancelled its turn's job. A subagent's own `subagent:sa-<n>` job
  was not listed again. Before, a subagent never showed: its turn's job was created inside the
  `start_subagent` call, so no event named it until it ended.
- **`report_status`.** Subagents gained a `report_status(status)` tool. `SUBAGENT_PROMPT` and the
  `building-a-simulation-scene` skill told them to call it when they start and at each major
  step. No model read it; `message_main_agent` pointed progress reports there.
- **`subagent_status` event.** `SubagentPool(on_status=…)` reported a `SubagentStatus` when a turn
  started (running, with its job id), on each `report_status`, and when the turn ended (succeeded,
  failed or cancelled, keeping the last text). The hub recorded it as a `TurnEvent` with an empty
  `turn_id` and sent it to `WatchConversation` subscribers. It never started a turn. The client
  applied it outside the turn's seq gate (a later status per subagent won), so it never moved the
  turn phase or the transcript.
- **Code.** `proto/surmap/agent/v1/chat.proto` (`SubagentStatus`, `TurnEvent.subagent_status`),
  `runtime.events.SubagentStatus`, `subagents.REPORT_STATUS`, `ChatHub._subagent_status`,
  `web/agent-chat/src/components/TasksPanel.tsx`, `src/view-model/tasks.ts`.
- **Tests.** pytest: 10 subagent-status (pool and hub) and 1 event mapping. vitest: 6 reducer and
  5 panel. Playwright: 1 e2e.

Docs: [docs/agent.md](../../agent.md) (*Subagents*, *Event stream*, *Tasks panel*).
