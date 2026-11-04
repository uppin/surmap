# Changeset: The survey agent and its chat page on Modal, behind a pass code

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — more than one package (`surmap.agent`, `surmap.survey.modal_hosting`, `web/agent-chat`), a security gate across every rpc and route

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery companion
- [wf 2] ⏳ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] `tests/test_agent_access.py` — tokens: issued for the code only, verified, expired, tampered; header or cookie
  - [ ] `tests/test_agent_access_server.py` — the gate over the in-memory agent: sign-in, rpc and route refused/allowed, `/health` and the page open, no code = no gate; `--web-dist`
  - [ ] `tests/test_modal_survey_apps.py` — the agent app's shape (AST) and `agent_command`
  - [ ] `web/agent-chat` — `?code=` sign-in and header (App + adapter tests)
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `surmap.agent.server.access`; gate wrappers in `build_agent_description`; `/auth/session`; `--web-dist`
  - [ ] Config: `SURMAP_AGENT_ACCESS_CODE`, `--web-dist`
  - [ ] UI: sign-in, interceptor, same-origin default, unauthenticated hint
  - [ ] `modal_hosting.agent_command`, `src/surmap/agent/modal_agent_app.py`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (V1; V4 deploy on Modal)
  - [ ] `docs/agent.md` (access, `--web-dist`), `docs/modal.md` §5 (the agent app), changelog
  - [ ] Lint and quality gates green (Python four; UI lint, typecheck, test, build)

## Initial Discovery

Full codebase exploration that grounded this plan:
[initial-discovery.md](./2026-11-04-agent-on-modal-initial-discovery.md).

## Stack Context

Node 3, on `station-lifecycle-agent-ui` (#113), which is on #112.

### Inherited Dependencies — do not implement here

- `--station modal` and `ModalStationControl` (#113); the station app fixes (#112).

## Technical Changes

### State A (Current)

No auth; loopback by default; the page is served by Vite or `vite preview`, pointed at the agent
with `?server=`; no Modal app for the agent.

### State B (Target)

PRD R1–R5. `AccessGate(code, clock, ttl_s=43200)`: `issue(code) -> str | None`,
`allows(token) -> bool`; token `<expiry>.<hmac-sha256(key, expiry)>`, key = sha256 of
`surmap-agent-session:` + code; `session_token(headers)` reads `authorization: Bearer` then the
`surmap_session` cookie.

## Verification

**Method:** V1-fail→pass — the tests above; V4 — deploy on Modal and use it.
**Command:** `uv run pytest -q tests/test_agent_access*.py tests/test_modal_survey_apps.py` ·
`cd web/agent-chat && yarn test --run`
**Before:** the new tests fail (no `surmap.agent.server.access`, no gate, no app file).
**After:** all pass.
V4: deploy station, CM5 and agent on `ginas-bb`; the agent URL without a code shows the hint and
its rpc answers `UNAUTHENTICATED`; with `?code=` the chat works, the SAM chip starts the station.
**Approved:** the developer, 2026-11-04 ("deploy … chat app + CM5 + station to Modal").

## Decisions & Trade-offs

- Stateless signed tokens (key from the code): they survive a container restart and the code is
  the only secret; rotating it revokes all sessions.
- The cookie beside the header: `<img>` and the GLB loader cannot send headers; same origin keeps
  it first-party. Connect calls send the header, as specified.
- No rate limit on `/auth/session` in this PR; the code should be long and random.
