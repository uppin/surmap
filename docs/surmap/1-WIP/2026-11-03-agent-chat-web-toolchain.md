# Changeset: Web toolchain for the agent chat — Vite, React, TypeScript, Tailwind, shadcn/ui, connect-es

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Infra
**Behaviour**: preserves
**Complexity**: 3 — new toolchain and CI workflow, generated TS client from proto; no Python change

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-ft-dev` Plan — changeset with a V3 `## Verification` and its before-output · this file + discovery (commit 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation — None — Infra, no user-visible behaviour delta
  - [x] Create changeset
  - [ ] Before-output re-recorded on the branch tip (commit 2)
- [wf 2] ⬜ `/green` Implement — the recorded command produces the planned after-output ·
  - [ ] `web/agent-chat/` scaffold: Vite 7, React 19, TypeScript 5 strict, Tailwind 4, ESLint, Vitest
  - [ ] shadcn/ui initialised (`components.json`, `src/components/ui/{button,card,textarea,scroll-area,badge,separator}.tsx`, `src/lib/utils.ts`)
  - [ ] `buf.gen.yaml` + `npm run gen` → `src/gen/surmap/agent/v1/*_pb.ts` via `@bufbuild/protoc-gen-es` v2 from `proto/surmap/agent/v1`
  - [ ] Placeholder page renders the shadcn `Card` with the list of `SurveyTools` rpcs from the generated descriptor
  - [ ] `.github/workflows/agent-chat.yml`: `npm ci`, `npm run gen` + `git diff --exit-code`, `lint`, `typecheck`, `test`, `build`
  - [ ] The V3 command produces the After output below
- [wf 3] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `web/agent-chat/README.md` — dev, gen, test and build commands
  - [ ] `README.md` — one line pointing at `web/agent-chat/`
  - [ ] `docs/surmap/changelog/2026-11-03-agent-chat-web-toolchain.md` — write changelog entry

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-agent-chat-web-toolchain-initial-discovery.md](./2026-11-03-agent-chat-web-toolchain-initial-discovery.md).

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **6 of 9** · #pending
**Branch**: `pr-6-survey-agent` · **Base**: `pr-5-survey-agent`
**Successor**: `pr-7-survey-agent`
**Kind**: Infra · behaviour-preserves
**Workflow**: preset `infra` · planned by `/plan-pr-stack` · pass-2 = the V3 command and its recorded before-state

Why the boundary falls here: the repo has no JavaScript toolchain; landing one (and its CI) apart
from the chat UI keeps the UI PR about behaviour and lets the toolchain go green in wave 1.

### Owned API surface

- `web/agent-chat/` (package, configs, `components.json`, shadcn primitives, `buf.gen.yaml`, placeholder `App.tsx`)
- `.github/workflows/agent-chat.yml`

### Green wave

**Wave:** 1 of 4
**Node:** n6
**Concurrent with:** n1, n2, n3, n4, n5
**Blocks:** n9 (builds the chat UI in this package)

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9

### Greenable independently?

**yes** — codegen reads `proto/surmap/agent/v1/*.proto`, which n1's red commit adds; the toolchain
does not need n1's Python implementation.

### Trunk-merge safety

**When this PR merges alone:** Python CI (`ci.yml`) unchanged; a new, path-filtered workflow runs
only on `web/agent-chat/**` and `proto/surmap/agent/**`. **Local dev data:** no. **Production
data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `proto/surmap/agent/v1/*.proto` | n1 | present from n1's red commit | generates TS from it; never edits it |

**Greenable independently?** yes.

## Inherited Restructure — expect rewrite

n2 moves the demo run engine; this node touches no Python. No fallout expected.

## Affected Packages

- **web/agent-chat** (new); `.github/workflows/agent-chat.yml` (new); root `.gitignore` (`web/agent-chat/node_modules`, `dist`)

## Related Feature Documentation

None — Infra, no user-visible behaviour delta. No PRD.

## Summary

A Vite + React + TypeScript app with Tailwind and real shadcn/ui (`components.json`, Radix-based
primitives copied into `src/components/ui`), connect-es v2 / protobuf-es v2 code generated from the
agent protos, and a CI workflow that checks generation, lint, types, tests and the build.

## Background

The demo UI is HTML/JS inside Python strings (`demo/page.py`), with no npm anywhere. The developer
asked for a shadcn chat UI; that needs a real frontend package.

## Scope

- Toolchain, shadcn init, codegen, placeholder page, CI
- **Out of scope:** chat behaviour (n9)

## Technical Changes

### State A (Current)

No `package.json` in the repo; workflows `ci.yml`, `bevy-wasm-build.yml`, `bevy-wasm-test.yml`.
Local toolchain: node v20.19.5, npm (bundled); no pnpm.

### State B (Target)

```text
web/agent-chat/
  package.json  package-lock.json  tsconfig*.json  vite.config.ts  eslint.config.js
  components.json  buf.gen.yaml  index.html
  src/{main.tsx,App.tsx,index.css,lib/utils.ts}
  src/components/ui/{button,card,textarea,scroll-area,badge,separator}.tsx
  src/gen/surmap/agent/v1/{execution,survey_tools,jobs,chat}_pb.ts
  src/App.test.tsx
.github/workflows/agent-chat.yml
```

### Delta (What's Changing)

#### web/agent-chat

- all files above (new)

## Verification

**Method:** V3 — a deterministic command whose before- and after-output are recorded here
**Command:** `cd web/agent-chat && npm ci && npm run gen && git diff --exit-code src/gen && npm run lint && npm run typecheck && npm test -- --run && npm run build`
**Before:**

```text
$ cd web/agent-chat
(eval):cd:1: no such file or directory: web/agent-chat
```

**After:** every step exits 0; `npm test` reports the placeholder test passing (it lists the
`SurveyTools` rpcs from the generated descriptor); `npm run build` writes `dist/index.html` and
`dist/assets/*.js`; the `agent-chat` workflow is green on the PR.

## Decisions & Trade-offs

- **npm, not pnpm**: node 20 ships npm; pnpm is not installed on the dev machine and adding it is a
  tooling change the developer did not ask for. `package-lock.json` pins versions.
- **Real shadcn/ui** (`components.json` + Radix primitives copied in), not hand-rolled look-alikes.
- **connect-es over the Connect protocol** (`@connectrpc/connect-web`), which supports unary and
  server-streaming over `fetch` — no NDJSON/REST transcoding layer.
- **Generated TS is checked in** and CI fails on drift, matching how the Python `_pb2` files are kept.
