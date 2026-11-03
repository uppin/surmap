# The survey agent runs as a chat server process

**Date:** 2026-11-03
**Feature:** Survey agent / chat server (`#survey-agent` 8/9, PR #84)

- **Process.** `python -m surmap.agent` serves `ChatService`, `AgentJobs`
  and `SurveyTools` over Connect plus `/health`, `/geometry/…glb` and
  `/frames/…jpg` on hypercorn, `127.0.0.1:8780` by default; CORS for
  `SURMAP_AGENT_CORS_ORIGINS` (default the Vite origin). Ctrl-C stops it
  cleanly.
- **Hub.** `surmap.agent.server.ChatHub` owns one `AgentSession` per
  conversation and fans its events out to `StreamTurn` and
  `WatchConversation` subscribers; `ChatService` maps runtime events to
  `TurnEvent`s.
- **Binding.** `SurveyTools` handlers and job tools are bound as agent
  tools; tool images reach the stream, the model reads a placeholder.
- **Limits.** `--sam-fake` only; recorded follow-ups in
  `src/surmap/docs/todo/2026-11-03-agent-cli-sam-flags.md`,
  `src/surmap/docs/todo/2026-11-03-agent-tool-image-parts.md` and
  `src/surmap/docs/code-issues/private-reach-agent-server-hub.md`.
- **Tests.** `tests/test_agent_chat_service{,_errors}.py`,
  `tests/test_agent_server_{app,binding,e2e,events,routes}.py` (79).
- **Verified.** Full suite 1628 passed, 32 skipped; smoke run
  `--sam-fake --port 0` answered `/health` 200 and a CORS preflight; a
  live Ollama turn (`fastcontext-tools:latest`) answered "What demos can
  you run?" with two tool calls and `turn_finished(STOP)`.

Docs: [docs/agent.md](../../agent.md).
