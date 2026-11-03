# The survey agent has a chat UI

**Date:** 2026-11-03
**Feature:** Survey agent / chat UI (`#survey-agent` 9/9, PR #85)

- **Shape.** `web/agent-chat` talks to the agent only through a
  `ChatPort` (`src/ports.ts`) backed by a Connect adapter over the
  generated client; a pure `chatReducer` turns `TurnEvent`s into
  transcript, jobs and turn-phase state. Components are presentational.
- **Page.** Streamed Markdown transcript, tool-call cards with resolved
  execution policy and status, a composer that never locks (Send idle,
  Steer + Stop busy), a jobs panel with Cancel, inline tool images, a
  lazily loaded three.js GLB preview, a model picker, the
  `WatchConversation` stream for job-started turns, and history restore
  from `GetConversation`. `?server=` (default `http://127.0.0.1:8780`)
  and `?conversation=` (default one per tab).
- **Bundle.** three.js is split into core, renderer and loader chunks
  (`vite.config.ts` `codeSplitting` groups), each under Vite's 500 kB
  warning, all loaded only with a preview.
- **Tests.** 86 vitest (reducer, components, adapter, lock resolver) and
  9 Playwright flows against a stub Connect server (`e2e/`); CI installs
  Chromium and runs both.
- **Verified.** A manual run against `python -m surmap.agent --sam-fake`
  with `ollama:fastcontext-tools:latest`: "what demos can you run?"
  drew a `list_demos` step (`SYNC 10 s → FAIL`, Done) and the reply
  "The station can run 3 demo scenes, all currently unprepared." in 16 s.

Docs: [docs/agent.md](../../agent.md#chat-ui),
[web/agent-chat/README.md](../../../web/agent-chat/README.md).
