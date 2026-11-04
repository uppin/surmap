# Changeset: Simulation as a right-side pane inside the chat

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — one package (`web/agent-chat`), a handful of owned symbols, unit/component tests only

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + companion
  - [x] Classify (Feature · adds), place in `docs/agent/1-WIP/`
  - [x] Discovery companion written
  - [x] User decisions recorded (trigger / content / layout)
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 3 suites red on missing implementation, 15 existing tests green
  - [x] View-model tests for simulation derivation from the transcript
  - [x] `SimulationPane` component tests
  - [x] Chat-page test: a created simulation shows in the right pane
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · 153 tests green, typecheck/lint/build green
  - [x] `simulationFromTranscript` view-model
  - [x] `SimulationPane` component (live `/sim/` iframe)
  - [x] ChatPage right-column layout (simulation above Jobs)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/agent.md` — chat UI section names the simulation pane

## Initial Discovery

Full exploration: [2026-11-04-simulation-right-pane-initial-discovery.md](./2026-11-04-simulation-right-pane-initial-discovery.md).

## Decisions (user, 2026-11-04)

- **Trigger**: only `create_scenario` — the pane appears when the agent
  creates a simulation, not for a pre-existing scenario.
- **Content**: live simulation — embed `/sim/?scenario=<id>` in an iframe,
  with name/version header, credits, and an open-full-page link.
- **Layout**: right column — chat transcript/composer on the left; the right
  column stacks the simulation pane above the Jobs panel. Map stays above.
  Narrow screens stack vertically.

## State A

The chat page shows the map on top and Jobs at the right of the transcript.
A simulation the agent builds opens only as a separate `/sim/` page; the
person must follow the URL the agent reports.

## State B

When a `create_scenario` tool call succeeds in the conversation (or the
agent's reply reports the `/sim/?scenario=<id>` URL of a scene its subagent
built), the chat shows a right-side Simulation pane: the scenario name and
version, its credits, an "Open simulation" link, and the live Bevy page in
an iframe. Later scenario edits for the same id bump the shown version and
reload the iframe. No creation in the transcript → no pane. Reloading the
page restores the pane from the replayed history.

## Delta

- New `web/agent-chat/src/view-model/simulation.ts` (+ tests): pure
  derivation of the created simulation from transcript items.
- New `web/agent-chat/src/components/SimulationPane.tsx` (+ tests).
- `web/agent-chat/src/ChatPage.tsx`: right-column layout when a simulation
  exists; unchanged layout otherwise.

## Verification

- Red (before implementation): 3 new suites failed on the missing
  view-model/component/pane; 15 pre-existing tests in those files passed.
- `yarn test --run`: 153 passed / 16 files, repeated 6× green. One earlier
  full-suite run showed 1 unidentified failure under load; not reproduced
  in 6 subsequent runs, and the untouched base passes (135 tests).
- `yarn typecheck`: green. `yarn lint`: green (2 pre-existing warnings in
  `src/components/ui/`). `yarn build`: green.
- `yarn e2e` (Playwright/Chromium, stub server): 12 passed, including a new
  test that a created simulation shows in the right-side pane.
- Not done: no commit/PR (none requested), so wf 4 wrap remains open.
