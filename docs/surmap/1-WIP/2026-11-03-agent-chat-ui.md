# Changeset: Survey agent chat UI — shadcn transcript, tool steps, jobs, steering

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — streaming client state with concurrent steer/cancel, generated client, three.js preview, Playwright against a stub server

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (commit 1 · `f67569a`)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 70 vitest + 8 Playwright failing — commit 2
  - [x] Create failing acceptance tests
  - [x] Run acceptance tests (verify they fail)
  - [x] TDD Red — write failing unit/integration tests
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: `ChatPort` (ports) + Connect adapter over the generated client (`createAgentTransport`, `createConnectChatPort`); `chatReducer`, `isTurnActive`, `policyLabel`, `jobElapsedMs` from `TurnEvent`s
  - [ ] Milestone 2: transcript, Markdown, tool steps with policy and status
  - [ ] Milestone 3: composer (send / steer / stop), jobs panel with cancel
  - [ ] Milestone 4: frame images, GLB preview (three.js `GLTFLoader`), model picker, watch stream, history restore
  - [ ] Milestone 5: `App` wires the port, reducer and components (`?server=` default `http://127.0.0.1:8780`, `?conversation=` else one id per tab); replaces n6's placeholder page and its `App.test.tsx`
  - [ ] `.github/workflows/agent-chat.yml`: install Chromium (`yarn playwright install --with-deps chromium`) and run `E2E_REQUIRE_BROWSER=1 yarn e2e`
  - [ ] Acceptance: `yarn test --run` (vitest) and `yarn e2e` (Playwright against the stub server) pass
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (plus one manual run against `python -m surmap.agent --sam-fake`, or why not)
  - [ ] `docs/agent.md` — "Chat UI" section with a screenshot
  - [ ] `web/agent-chat/README.md` — running against a local agent server
  - [ ] `docs/surmap/changelog/2026-11-03-agent-chat-ui.md` — write changelog entry
  - [ ] Validate tests (`/validate-tests`)

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-agent-chat-ui-initial-discovery.md](./2026-11-03-agent-chat-ui-initial-discovery.md).

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **9 of 9** · [#85](https://github.com/uppin/surmap/pull/85)
**Branch**: `pr-9-survey-agent` · **Base**: `pr-8-survey-agent`
**Successor**: none — top of stack
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing vitest and Playwright tests

Why the boundary falls here: the UI is a client of the `ChatService` contract; it is tested against a
stub of that contract and only needs the real server for the wrap-time manual run.

### Owned API surface

- `web/agent-chat/src/ports.ts` (`ChatPort`), `src/adapters/connect-chat.ts`
- `web/agent-chat/src/view-model/{transcript,jobs,chat-reducer}.ts`
- `web/agent-chat/src/components/{Transcript,ToolStep,JobsPanel,Composer,ModelPicker,FrameImage,GeometryPreview}.tsx`
- `web/agent-chat/e2e/` (Playwright + stub Connect server), `playwright.config.ts`, `scripts/e2e.mjs`
- `web/agent-chat/src/test-support/` (event script builder, reducer driver, view-item builders)

### Green wave

**Wave:** 4 of 4
**Node:** n9
**Concurrent with:** none — this node is alone in its wave
**Blocks:** nothing

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9

### Greenable independently?

**no — blocked by n6 and n8**: the tests build in n6's package with its generated client; the
wrap-time manual check needs n8's server. The vitest and Playwright suites themselves use a stub, so
once n6 is green they are this node's own.

### Trunk-merge safety

**When this PR merges alone:** only `web/agent-chat` changes; Python CI unaffected. **Local dev
data:** none. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `web/agent-chat` toolchain, shadcn primitives, `src/gen/*` | n6 | real after n6 green | builds on them; adds shadcn components with the CLI when needed |
| `proto/surmap/agent/v1/chat.proto` messages | n1 | real from n1's red commit | consumes them via generated TS |
| the running server | n8 | real after n8 green | only for the wrap-time manual run |

**Greenable independently?** no — needs n6 green first (n8 for the manual check). Red step: n6 is green, and no red test reaches a predecessor stub (no `TODO(pr-<k<9>)` in `web/agent-chat`), so every vitest and Playwright failure is this node's own.

## Inherited Restructure — expect rewrite

n2 moves the demo run engine; this node is TypeScript only. No fallout expected.

## Affected Packages

- **web/agent-chat**.

## Related Feature Documentation

- PRD: [PRD-2026-11-03-agent-chat-ui.md](./PRD-2026-11-03-agent-chat-ui.md)

## Summary

A React client in hexagonal shape: a `ChatPort` the components never bypass, a Connect adapter, and
a pure reducer turning `TurnEvent`s into transcript and jobs state — so the behaviour is unit-tested
without a browser, and Playwright checks the wiring against a stub server.

## Background

See the PRD. Steering is the behaviour that differs from a usual chat: the composer never locks
while a turn runs.

## Scope

- Transcript, tool steps, jobs panel, composer with steer/stop, images, GLB preview, model picker, watch stream, history restore
- **Out of scope:** auth, multi-user, persistence beyond the server's in-memory store

## Technical Changes

### State A (Current)

After n6: a Vite/React/TS/Tailwind/shadcn package with generated `surmap.agent.v1` TS and a
placeholder page.

### State B (Target)

```ts
interface ChatPort {
  streamTurn(input: { conversationId: string; modelId: string | null; text: string }, signal: AbortSignal): AsyncIterable<TurnEvent>;
  watch(conversationId: string, signal: AbortSignal): AsyncIterable<TurnEvent>;
  steer(conversationId: string, text: string): Promise<SteerOutcome>;   // { accepted }
  cancelTurn(conversationId: string): Promise<void>;
  cancelJob(conversationId: string, jobId: string): Promise<void>;     // conversation → surmap-conversation-id header
  listModels(): Promise<ModelInfo[]>;                                  // ModelInfo.isDefault from default_model_id
  getConversation(conversationId: string): Promise<TurnEvent[]>;
}
function createConnectChatPort(transport: Transport): ChatPort;
function chatReducer(state: ChatState, action: ChatAction): ChatState;
// ChatAction: turn_requested | event{event, at} | history_loaded{events, at} | stop_requested
//             | stream_failed{message} | models_loaded{models} | model_selected{modelId}
// TurnPhase: idle | starting | running | stopping; events at or below lastSeq are ignored
```

Components are presentational (props + callbacks); only `App` holds the port. Accessible names the
tests and the Playwright page object use: `log "Conversation"`, `group "Tool call <tool>"` with a
`status` named by its label (Running, Done, Failed, Detached, Cancelled), `region "Arguments"`,
`img "<tool> result"`, `figure "Object geometry preview"` (`data-geometry-url`), `region "Jobs"` with
`listitem "Job <id>"`, `textbox "Message"`, buttons `Send` / `Steer` / `Stop` / `Cancel`, native
`combobox "Model"` with options `<provider> · <name>`.

### Delta (What's Changing)

#### web/agent-chat

- files listed under Owned API surface; `package.json` adds `three` 0.186.1, `react-markdown` 10.1.0, dev `@types/three` 0.186.0, `@playwright/test` 1.64.1, `@testing-library/user-event` 14.6.8 (all served by the private registry, node 20 compatible; `yarn.lock` normalised with `yarn resolve-local-lock`), scripts `e2e` and a third `tsc -p e2e/tsconfig.json` in `typecheck`
- `.gitignore`: `web/agent-chat/test-results`, `playwright-report`

## Verification

**Method:** V1 — fail→pass reducer and component tests (vitest) and Playwright flows against a stub Connect server
**Command:** `cd web/agent-chat && yarn test --run && yarn e2e`
**Before:** red (commit 2) — `yarn test --run`: 70 failed, 14 passed (n6's App and lock-resolver tests); `yarn e2e`: 8 failed (n6's placeholder page has no chat) — every failure is `Error: TODO(pr-9): implement` or a role the stub components do not render yet
**After:** green; the `agent-chat` workflow runs both

## Testing Plan

- Reducer: event sequences → state (stream text, tool start/finish, detach, steer marker, job notice, cancel).
- Components: Testing Library with a fake `ChatPort`.
- Playwright: stub Connect server scripted per test (`e2e/stub-chat-server.ts`).

## Acceptance Tests

### web/agent-chat

Written red in commit 2; all fail on this node's missing implementation only.

- `src/view-model/chat-reducer.test.ts` (24) — user message; streamed text joined, new message after a tool call; tool step with its resolved policy (or none); succeeded / failed / frame image; detached and ASYNC calls move to jobs; steer marker; job notice for a job-event turn, panel-only update inside a turn; phases (starting, running, idle, stopping); cancelled turn; turn error and broken stream; seq de-duplication; history replay; default and chosen model
- `src/components/Composer.test.tsx` (9) — idle sends a turn (button, Enter), clears, ignores blank; offers Send idle, Steer + Stop busy; input enabled while busy; busy sends steer; Stop cancels
- `src/components/ToolStep.test.tsx` (13) — policy labels (`SYNC 30 s → DETACH`, `SYNC 10 s → FAIL`, `ASYNC`); five status labels; duration; job id; expand to arguments; frame image; geometry preview URL resolved against the server
- `src/components/JobsPanel.test.tsx` (6) — tool, status, elapsed (running and ended); Cancel only on running jobs; detail; empty state
- `src/components/Transcript.test.tsx` (6), `src/components/ModelPicker.test.tsx` (4), `src/adapters/connect-chat.test.ts` (8, in-memory Connect router: request fields, null model, event order, steer not accepted, cancel turn, job cancel header, default model, history)
- `e2e/chat.spec.ts` (8) — send → tool step with policy → Markdown reply; steer during a blocking call → marker + job; watch-stream job notice and reply; Stop; job Cancel names the conversation; frame image decodes and GLB preview draws a canvas; model picker sends the chosen id; reload redraws from `GetConversation`. `e2e/stub-chat-server.ts` scripts each test's turns and records what the page sent

## Decisions & Trade-offs

- **Reducer over a state library**: one pure function is the whole client behaviour and the cheapest thing to test.
- **three.js only for the preview card**, loaded lazily so the chat bundle stays small.
- **`cancelJob` takes the conversation** (State B had `cancelJob(jobId)`): n8's `AgentJobs` finds the
  job runner by the `surmap-conversation-id` header, so the port needs the conversation per call.
- **`modelId: string | null`** in `streamTurn` and **`ModelInfo.isDefault`**: `null` leaves the
  model to the server; the default flag carries `ListModelsResponse.default_model_id` through the port.
- **Presentational components, callbacks not the port**: `Composer`, `JobsPanel`, `ModelPicker`,
  `ToolStep` take props and callbacks, so their tests record callbacks; the port is exercised by the
  adapter tests (in-memory `createRouterTransport`) and the Playwright suite.
- **Native `<select>` for the model picker**, so it is a real `combobox` the tests can drive.
- **The stub server needs no new dependency**: `@connectrpc/connect-node` 2.2.0 needs node 22 and
  pins `@connectrpc/connect` exactly, so `e2e/stub-chat-server.ts` serves `createConnectRouter()`
  handlers through `createFetchHandler` (`@connectrpc/connect/protocol`) on `node:http`.
- **`yarn e2e` skips without Chromium** (`scripts/e2e.mjs`), unless `E2E_REQUIRE_BROWSER=1`, which
  CI sets after installing the browser.
