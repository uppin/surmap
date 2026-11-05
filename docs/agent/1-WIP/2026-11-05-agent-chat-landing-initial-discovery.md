# Initial Discovery: Agent chat landing page

## Combined Conclusions

- The chat page (`web/agent-chat`) renders the chat straight away at `/`. The only way in through
  the gate is `?code=` in the URL, which `App.tsx` trades once through `signIn`
  (`src/adapters/session.ts`, `POST /auth/session`) and then drops. A visitor who opens the bare
  URL sees a chat whose every call fails 401 / `UNAUTHENTICATED`, with no way to enter the code.
- The page cannot tell on its own whether the agent is gated or whether the tab is signed in. The
  token lives in `sessionStorage` (per tab), and the `surmap_session` cookie is HttpOnly. The
  server has no read-only session route: `POST /auth/session` exists only when gated, and every
  other `GET` but `/health` and the page's own files is refused when gated.
- `agent_http_routes` (`src/surmap/agent/server/routes.py`) dispatches every `GET` through one
  `serve` handler. A `GET /auth/session` answered there, ahead of the gate check, can say whether
  the agent is gated and whether the caller is signed in (bearer or cookie, `_signed_in`).
- The page writes `?conversation=` into the URL on mount, so a reload reopens the chat.
  Existing links (`/?code=…` in docs/modal.md, `/?conversation=…` in the e2e `ChatPage.open`)
  name the chat explicitly, so the landing can own the bare `/` without breaking them.
- The e2e stub server (`e2e/stub-chat-server.ts`) has no `/auth/session`. If the page treats a
  status it cannot read as "not gated", the Playwright suite keeps passing unchanged.

## Exploration 1: chat page and access gate — 2026-11-05

### Grep / glob

- `git grep -niE 'pass.?code'` → `src/surmap/agent/server/{access,routes,app}.py`,
  `web/agent-chat/src/adapters/session.ts`, `tests/test_agent_access*.py`, docs/agent.md,
  docs/modal.md.

### Inspected files

#### `web/agent-chat/src/App.tsx`
`?code=` → `signIn` → drop the code param → render `ChatPage`. Props `port` and `signIn` are the
test seams. The conversation id is created on mount and written to the URL right away.

#### `web/agent-chat/src/adapters/session.ts`
`signIn`, `storedToken`, `sessionInterceptor`, `defaultServerUrl`.

#### `src/surmap/agent/server/routes.py`, `access.py`
`AccessGate.issue` / `allows`; `session_token` reads the bearer header or the cookie. The `GET *`
handler serves the page and `/assets/` openly, then gates everything else.

#### `tests/test_agent_access_server.py`, `web/agent-chat/src/App.test.tsx`
In-memory host tests for the gate; App tests render `<App port={fake} />` with
`/?conversation=conv-9`. Two tests (`names a new conversation…`, `keeps the conversation…`) start
from a URL with no conversation and expect the chat.
