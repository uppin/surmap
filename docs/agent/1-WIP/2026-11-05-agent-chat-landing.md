# Changeset: Agent chat landing page behind the pass code

**Date**: 2026-11-05
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — two packages (agent server route + chat page), in-memory HTTP and jsdom tests, one new read-only route

## Workflow

- [wf 1] ✅ 2026-11-05 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion; requirements kept in § Scope (no separate PRD, small UI entry point)
- [wf 2] ✅ 2026-11-05 `/plan-red` Red — acceptance and failing lower-tier tests · 3 pytest + 4 adapter + 10 App tests red
- [wf 3] ✅ 2026-11-05 `/green` Green — implement until every red test passes · pytest 2671 passed, vitest 194, e2e 13
  - [x] `GET /auth/session` answers `{gated, signed_in}`
  - [x] `sessionStatus` adapter
  - [x] `LandingPage` — repo link, pass-code form, Open chat
  - [x] `App` routes landing ↔ chat
  - [x] The chat's bridge comes from config only (`VITE_SURMAP_BRIDGE_URL`), never `?bridge=`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] docs/agent.md — Access code + chat page sections name the landing and `GET /auth/session`
  - [ ] docs/modal.md — the deployed URL opens on the landing
  - [ ] Changelog entry in docs/surmap/changelog/

## Initial Discovery

Full codebase exploration that grounded this plan:
[initial-discovery.md](./2026-11-05-agent-chat-landing-initial-discovery.md).

## Summary

The chat app opens on a landing page. It links to the source repository
(https://github.com/uppin/surmap) and is the way into the chat. When the agent is gated, the way in
is the same pass code `POST /auth/session` already accepts.

## Scope

- The bare URL (no `?conversation=`, no `?code=`) shows the landing: the SurMap name, one line on
  what it is, a link to https://github.com/uppin/surmap, and the entry to the chat.
- Gated agent, tab not signed in: the entry is a pass-code field and **Enter chat**. A wrong code
  says so and stays on the landing. The right code opens the chat in a new conversation.
- Ungated agent, or a tab already signed in (bearer or cookie): the entry is **Open chat**.
- A chat URL (`?conversation=…`) on a gated agent in a tab that is not signed in shows the landing.
  After signing in it opens that same conversation.
- `?code=` keeps working: the code is traded and dropped, and the chat opens. A refused code now
  lands on the landing with the error instead of on a chat that cannot call anything.
- An agent that cannot answer `GET /auth/session` (an older server, the e2e stub) is treated as
  ungated, the same as before.

## Technical Changes

### State A (Current)

`/` renders the chat. `?code=` is the only sign-in. The page cannot ask whether it is gated or
signed in.

### State B (Target)

- `GET /auth/session` (always mounted, ahead of the gate) → `200 {"gated": bool, "signed_in": bool}`,
  with CORS for allowed origins. Ungated → `{"gated": false, "signed_in": true}`.
- `web/agent-chat/src/adapters/session.ts` `sessionStatus(serverUrl)` reads it (bearer when the
  tab has a token). A failed request or a non-200 answer reads as ungated.
- `web/agent-chat/src/LandingPage.tsx` is the new landing. `App.tsx` shows the landing or the
  chat, and writes `?conversation=` only once the chat opens.

## Verification

**Method:** V1-fail→pass — server route tests in `tests/test_agent_access_server.py`, landing and
routing tests in `web/agent-chat/src/App.test.tsx`, adapter tests in `session.test.ts`
**Command:** `uv run pytest -q tests/test_agent_access_server.py && (cd web/agent-chat && yarn test --run)`
**Before:** the new tests fail (no `GET /auth/session`, no landing)
**After:** all green, existing suites unchanged in count except the two App tests that now enter
through the landing

## Decisions & Trade-offs

- **The landing itself is public, and the gate guards the chat.** The repository is public, so
  hiding its link behind the code would protect nothing. The pass code still guards every agent
  call, as before.
- **The chat no longer takes `?bridge=`** (asked for during this change). A link could name any
  socket and the preview would stream the drone's camera there. The bridge is now build config
  only. The simulation page (`examples/bevy-sitl-poc/src/fleet/stream.rs`) still reads `?bridge=`
  from its own URL. That needs its own change (the agent serving the bridge to `/sim/` as config).
- **Status read from the server, not guessed client-side.** A new tab already holding the cookie
  goes straight to **Open chat**, and a local ungated agent never asks for a code.
