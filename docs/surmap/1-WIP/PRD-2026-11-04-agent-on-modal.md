# The survey agent and its chat page on Modal, behind a pass code — PRD

**Date**: 2026-11-04
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: [Survey agent](../../agent.md) — access code, session token, serving the page
- **Related Feature 1**: [Chat UI](../../agent.md#chat-ui) — `?code=` sign-in, same-origin default
- **Related Feature 2**: [Modal](../../modal.md) — the agent as a deployed Modal app

## Summary

Run the chat page and the agent on Modal at one public URL that is useless without a shared pass
code: the code, given once in the page's `?code=` query, is exchanged for a session token the
agent issues; every call then carries it.

## Requirements

- R1 **Access code.** With `SURMAP_AGENT_ACCESS_CODE` set, `POST /auth/session` with
  `{"code": …}` answers `{"token", "expires_in"}` and sets an HttpOnly, Secure, SameSite=Strict
  cookie with the same token; a wrong code is 401. The token is signed with a key derived from the
  code and expires (12 h); changing the code revokes every token.
- R2 **Gate.** Every Connect rpc needs `Authorization: Bearer <token>` (or the cookie), else
  `UNAUTHENTICATED`; every HTTP route but `/health`, `/auth/session` and the page's files needs it,
  else 401. Without an access code nothing is gated (local use is unchanged).
- R3 **Page.** `--web-dist <dir>` serves the built chat page at `/` (its `assets/` beside it).
- R4 **Sign-in.** The page exchanges `?code=` once, drops it from the URL, keeps the token in
  session storage, sends it on every Connect call; with no `?server=` a production build talks to
  its own origin. An unauthenticated agent shows "open this page with ?code=…".
- R5 **Modal app.** `src/surmap/agent/modal_agent_app.py`: one CPU container running the agent
  with `--station modal --web-dist`, the demo cache on a Volume, secrets `surmap-agent`
  (`MODEL_API_KEY`, `SURMAP_AGENT_ACCESS_CODE`) and `surmap-survey`.
