# Initial Discovery: the survey agent and its chat page on Modal, behind a pass code

## Combined Conclusions

- The agent server has no auth and binds loopback by default (`docs/agent.md` *Running the
  agent*); a public Modal URL would let anyone spend `MODEL_API_KEY` and start the GPU station.
- Connect handlers are wrapped per service in `build_agent_description` (`_allowing_origins`,
  `app.py:429-446`), so one more wrapper gates every rpc; `ctx.request_headers` carries the
  `authorization` and `cookie` headers. HTTP routes are `HttpRoute`s from `agent_http_routes`
  (`routes.py:70-120`): `GET /health`, `GET *` (sim, datasets, geometry, frames, thumbnails),
  `OPTIONS *`; `HttpRequest.headers` is a mapping.
- The page makes requests that cannot carry an `Authorization` header: `<img>` thumbnails
  (`DatasetGallery.tsx:84`), the three.js GLB load (`ToolStep.tsx:31`), `fetch(/datasets)`
  (`connect-chat.ts:100`) — so the session also travels as an HttpOnly cookie on the same origin.
- The page's server defaults to `http://127.0.0.1:8780` (`App.tsx:19`); served by the agent it
  should default to its own origin.
- Static file serving with path containment exists for `/sim/` (`sim_routes.py:55-101`).
- Modal app files are AST-tested (`tests/test_modal_survey_apps.py`); what they run lives in
  `surmap.survey.modal_hosting`. Inside a Modal container the SDK is authenticated as the
  workspace, so `--station modal` can look the station up with no token.
- In-memory host (`surmap.rpc.hosts.in_memory`): `client(...).unary(..., headers=)` and
  `http(method, path, headers=, body=)` — enough for every gate test.

## Exploration 1: agent server, routes, page requests — 2026-11-04

Read `src/surmap/agent/server/app.py`, `routes.py`, `sim_routes.py`, `src/surmap/rpc/http.py`,
`src/surmap/rpc/hosts/in_memory.py`, `web/agent-chat/src/App.tsx`, `adapters/connect-chat.ts`;
grepped the page for `fetch(`, `<img`, `src={`, `new URL(`. Findings as above.
