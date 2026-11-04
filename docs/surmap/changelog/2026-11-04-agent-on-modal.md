# The survey agent and its chat page on Modal, behind a pass code

**Date:** 2026-11-04
**Feature:** Survey agent / access; Chat UI / sign-in; Modal / `surmap-agent`

- **Access code.** `SURMAP_AGENT_ACCESS_CODE` puts the agent behind a shared pass code:
  `POST /auth/session` trades it for a 12 h signed token, also set as an HttpOnly cookie; every
  rpc (`UNAUTHENTICATED`) and API route (401) needs it, `/health` and the page's files do not.
  Unset, nothing is gated. Code: `surmap.agent.server.access`.
- **Page.** `--web-dist` serves the built chat page at `/`; the page signs in with `?code=` once,
  drops it from the URL, sends the token on every Connect call, and talks to its own origin.
- **Modal.** `src/surmap/agent/modal_agent_app.py` (`surmap-agent`): one CPU container running
  the agent with `--station modal`, its page and a demo-cache Volume.
- **Verified** on Modal (`ginas-bb`, 2026-11-04) with the station and the CM5 deployed beside it.
- **Tests.** `tests/test_agent_access.py` (10), `tests/test_agent_access_server.py` (11), two app
  tests in `tests/test_modal_survey_apps.py`; `src/adapters/session.test.ts` (6), two App tests.

Docs: [docs/agent.md](../../agent.md) (*Running the agent*, *Chat UI*), [docs/modal.md](../../modal.md) §5.
