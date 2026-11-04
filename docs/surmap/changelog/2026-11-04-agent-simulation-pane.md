# Simulation as a right-side pane in the chat

**Date:** 2026-11-04
**Feature:** Survey agent / chat UI

- **Simulation pane.** When the agent created a simulation in the conversation — a succeeded
  `create_scenario`, or a reply reporting the `/sim/?scenario=<id>` URL of a scene a subagent
  built — the chat page showed it in a right-side pane: the scenario's name, version and
  credits, an Open simulation link, and the live Bevy page at `/sim/` in an iframe, with the
  Jobs panel below it. Later edits to that scenario bumped the version and reloaded the
  iframe; no creation, no pane, and a reload restored it from the replayed history.
- **Derivation.** `web/agent-chat/src/view-model/simulation.ts` read the created scenario
  from the transcript; `SimulationPane` rendered it. No new network calls.
- **Tests.** Vitest: 11 view-model, 5 component, 2 chat-page; Playwright: 1 e2e against the
  stub server.

Docs: [docs/agent.md](../../agent.md) (*Chat UI — Simulation pane*).
