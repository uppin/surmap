# Changeset: Survey agent chat UI — shadcn transcript, tool steps, jobs, steering

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — streaming client state with concurrent steer/cancel, generated client, three.js preview, Playwright against a stub server

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (commit 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: `ChatPort` (ports) + Connect adapter over the generated client; `chatReducer` view model from `TurnEvent`s
  - [ ] Milestone 2: transcript, Markdown, tool steps with policy and status
  - [ ] Milestone 3: composer (send / steer / stop), jobs panel with cancel
  - [ ] Milestone 4: frame images, GLB preview (three.js `GLTFLoader`), model picker, watch stream, history restore
  - [ ] Acceptance: `npm test -- --run` (vitest) and `npm run e2e` (Playwright against the stub server) pass
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

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **9 of 9** · #pending
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
- `web/agent-chat/e2e/` (Playwright + stub Connect server)

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

**Greenable independently?** no — needs n6 green first (n8 for the manual check).

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
  streamTurn(req: { conversationId: string; modelId: string; text: string }, signal: AbortSignal): AsyncIterable<TurnEvent>;
  watch(conversationId: string, signal: AbortSignal): AsyncIterable<TurnEvent>;
  steer(conversationId: string, text: string): Promise<SteerOutcome>;
  cancelTurn(conversationId: string): Promise<void>;
  cancelJob(jobId: string): Promise<void>;
  listModels(): Promise<ModelInfo[]>;
  getConversation(conversationId: string): Promise<TurnEvent[]>;
}
function chatReducer(state: ChatState, action: ChatAction): ChatState;
```

### Delta (What's Changing)

#### web/agent-chat

- files listed under Owned API surface; `package.json` adds `three`, `react-markdown`, `@playwright/test`

## Verification

**Method:** V1 — fail→pass reducer and component tests (vitest) and Playwright flows against a stub Connect server
**Command:** `cd web/agent-chat && npm test -- --run && npm run e2e`
**Before:** red — components and reducer are stubs
**After:** green; the `agent-chat` workflow runs both

## Testing Plan

- Reducer: event sequences → state (stream text, tool start/finish, detach, steer marker, job notice, cancel).
- Components: Testing Library with a fake `ChatPort`.
- Playwright: stub Connect server scripted per test (`e2e/stub-chat-server.ts`).

## Acceptance Tests

### web/agent-chat

- `src/view-model/chat-reducer.test.ts` — streamed text; tool step with policy label; detached step moves to jobs; steer marker; job notice; cancel
- `src/components/Composer.test.tsx` — idle sends a turn; busy sends steer; Stop cancels
- `e2e/chat.spec.ts` — send → tool step → reply; steer during a blocking call; frame image and geometry preview render; model picker

## Decisions & Trade-offs

- **Reducer over a state library**: one pure function is the whole client behaviour and the cheapest thing to test.
- **three.js only for the preview card**, loaded lazily so the chat bundle stays small.
