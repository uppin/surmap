---
name: troubleshoot-agent-conversation
description: Reconstruct a Agent conversation from a session URL or session ID — turns, tool calls, nested RPC methods, and  Request IDs — then hand off a chosen request ID to /trace-request. Use when the user pastes a the CI host/app-agent/admin/#/sessions/<uuid> URL, a session UUID, or asks what the agent did in a conversation.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob, Agent
---

> **Genericized import.** This workflow was originally written for a specific product and infrastructure. Service, artifact, dashboard and host names below are `example` placeholders — substitute SurMap's equivalents (see `README.md` and `docs/architecture.md`) before acting, and confirm any external system exists before calling it.


# Troubleshoot Agent Conversation

Peer of `trace-request`. That skill starts from a **Request ID** and reconstructs one request. **This skill starts from a Agent session** (admin URL or UUID), reconstructs the conversation (turns, tools, nested RPCs), extracts the request IDs those turns/tools used, and only then hands a specific ID to `/trace-request`.

## Invocation

```
/troubleshoot-agent-conversation <sessionUrl-or-sessionId> [question]
```

`$ARGUMENTS` is a session URL or UUID, optionally followed by a free-form question.

Examples:

- `<service-url>`
- `33145604-55e4-4879-8447-05d344ef6bcd why did icon generation stall?`
- `33145604-55e4-4879-8447-05d344ef6bcd which request IDs are icon generation?`

If no question is given, default to "reconstruct the conversation, list tool calls, and collect  Request IDs for `/trace-request`."

---

## Phase 0 — Parse the invocation

Extract `SESSION_ID` (UUID) and `QUESTION` (the rest). The UUID may be buried in a hash URL.

```bash
ARGS="$ARGUMENTS"
SESSION_ID="$(printf '%s\n' "$ARGS" | grep -Eo '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}' | head -1)"
QUESTION="$(printf '%s\n' "$ARGS" | sed -E "s|https?://[^ ]+||g; s|$SESSION_ID||g" | xargs)"
echo "sessionId: $SESSION_ID"
echo "question:  ${QUESTION:-reconstruct the conversation}"
echo "admin:     <service-url>"
```

If no UUID is found, stop and ask for a session URL or ID. Report `sessionId` and the question before querying.

---

## Phase 1 — Auth

Same gateway as `trace-request`:

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 check-auth
```

Exit 0 = good. Exit 4 = run `login` (requires browser). Token lasts ~24h.

Call tools as `npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 call <server>__<tool> '<json>'`.

The Agent Admin MCP is **`app-agent`** (`<service-url>`). It is not in this repo's `.muse/mcp.json` / `.mcp.json`; the CLI still reaches it after login.

Smoke-check:

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call app-agent__app_admin_whoami '{}'
```

---

## Phase 2 — Session identity (small, always complete)

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call app-agent__app_admin_list_sessions \
  '{"sessionId":"<SESSION_ID>","includeDuration":true}'
```

Capture: `title`, `status`, `agentName`, `source`, `userEmail`, `userId`, `projectId`, `metaSiteId`, `codexVersionId`, `createdAt`, `updatedAt`, `durationMs`, `sentiment`.

Also:

```bash
# entry-type histogram
call app-agent__app_admin_query_session_entries \
  '{"sessionId":"<SESSION_ID>","mode":"count_by_entry_type"}'

# tool histogram
call app-agent__app_admin_query_session_entries \
  '{"sessionId":"<SESSION_ID>","mode":"count_by_tool_name"}'

# project assets produced in this conversation
call app-agent__app_admin_get_session_project_assets \
  '{"sessionId":"<SESSION_ID>"}'

# optional
call app-agent__app_admin_list_feedback \
  '{"conversationId":"<SESSION_ID>","limit":20}'
```

`query_session_entries` `mode=rows` has 500'd — prefer `count_by_*` plus the per-turn tools below. Supported modes include `count_by_entry_type`, `count_by_tool_name`, `count_tool_errors_by_tool_and_response`.

Persist every MCP response to a file under `/tmp/app-session-<short>/`. Inner JSON from `content[0].text` is what matters.

---

## Phase 3 — Truncation (do not skip)

`@mcp-s/cli` clips large tool results at **~100k characters**. `get_session_messages`, `get_session_events`, `get_session_entries`, and unfiltered `query_session_timeline` will be **incomplete** on a real conversation.

Rules:

- Treat a 100k inner payload as truncated. Salvage complete JSON objects with `json.JSONDecoder.raw_decode`; never `json.loads` the clipped string.
- Prefer **aggregates** (Phase 2) and **per-turn** `query_session_timeline` (`turnId` set) over full dumps.
- Collect the **complete** request-ID list from Grafana (Phase 4), not from the clipped events dump.
- A Request ID looks like `1786956672.3961006910311412` (`epoch.digits`). Ignore values like `mnmis` / `qtwaj` — those are `ask_user` / tool-call ids stuffed into a `requestId` field.

---

## Phase 4 — Turn request IDs (Grafana)

The streamed user-turn IDs live on `surmap.onboard.session`. Time window = `createdAt − 5min` through `updatedAt + 10min` from Phase 2. Always pass ISO-8601 with a `Z`.

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call grafana-datasource__query_app_logs '{
    "sql": "SELECT timestamp, request_id, message FROM app_logs WHERE $__timeFilter(timestamp) AND artifact_id = '\''surmap.onboard.session'\'' AND message LIKE '\''%Start duplexer turn for session <SESSION_ID>%'\'' ORDER BY timestamp LIMIT 50",
    "fromTime": "<from_iso>",
    "toTime": "<to_iso>"
  }'
```

This is the authoritative turn → request ID list (one ID per user message). SQL **must** include `LIMIT` (max 100).

---

## Phase 5 — Conversation flow

**5a. Timeline, one turn at a time** (avoids the 100k clip):

```bash
call app-agent__app_admin_query_session_timeline \
  '{"sessionId":"<SESSION_ID>","turnId":"<turnId>","days":14}'
```

Waterfall `kind`s: `model`, `tool`, `phase`, `task`, `wait`. Tool rows' `label` is the tool name (`skill`, `invoke_rpc`, `generate_image`, …). `wait` rows are often `ask_user` pauses and can span hours.

Turn IDs come from the (possibly truncated) all-turns timeline, from events, or from log-payload refs:

```bash
call app-agent__app_admin_list_session_log_payloads \
  '{"sessionId":"<SESSION_ID>"}'
```

**5b. Events for labels / jobs / assets** — `get_session_events`. Salvage objects if clipped. Useful `eventType`s:

| eventType | Use |
|---|---|
| `TOOL_CALL_LABEL_UPDATED` | `toolName`, `toolCallId`, user-visible `displayLabel` |
| `TOOL_CALL_JOB_UPDATED` | async jobs (`processJob.title` e.g. `"Generating icons"`) |
| `AGENT_MENTIONED_ASSETS` | assets the model cited |
| `ASK_USER_REQUESTED` | questions shown to the user |
| `TURN_SUMMARY_GENERATED` | one-line turn summary |
| `MODEL_USAGE_RECORDED` | model + token counts |

**5c. Nested RPC methods** — turn request IDs are shared with downstream services. To see *which* RPC ran:

```bash
# tight window around that turn
call grafana-datasource__query_app_logs '{
  "sql": "SELECT timestamp, data FROM app_logs WHERE $__timeFilter(timestamp) AND request_id = '\''<turnRequestId>'\'' AND artifact_id = '\''surmap.onboard.session'\'' AND message = '\''[invoke_rpc] request'\'' ORDER BY timestamp LIMIT 20",
  "fromTime": "<turn_iso>",
  "toTime": "<turn_iso_plus_a_few_min>"
}'
```

`data` JSON has `service`, `method`, `fqdn`, `requestJson` (prompt, `assetId`, style, count, `conversationId`).

To confirm a downstream service actually ran under that ID:

```sql
SELECT request_id, count() AS c
FROM app_logs
WHERE $__timeFilter(timestamp)
  AND artifact_id = '<downstream-artifact>'
  AND request_id IN ('<id1>','<id2>',...)
GROUP BY request_id
ORDER BY c DESC
LIMIT 20
```

**5d. Model blobs (optional)** — `list_session_log_payloads` then `get_session_log_payload` with `sessionId` + `blobId` for the exact model request/response.

---

## Phase 6 — Answer, then hand off

Lead with the conversation, then the request IDs. Do **not** run `/trace-request` on every ID — list them, and trace only the ones the question needs (or ask which to trace).

```markdown
## Agent Conversation — <sessionId>
**Admin:** <service-url>
**UTC:** <createdAt> → <updatedAt> · **User:** <email> · **Agent:** <agentName>
**Project:** <projectId> · **Question:** <question>

### Answer
<1–3 sentences. If the question is "which request IDs are X", list those IDs here.>

### Turns
| # | UTC | turnId | requestId | tools / nested RPC | result |
|---|-----|--------|-----------|--------------------|--------|
| 1 | … | … | `epoch.digits` | skill, scrape_url | … |

### Tool calls (session)
| tool | count |
|------|-------|

### Request IDs for /trace-request
- `<id>` — turn N, <what happened>
- For nested work (icons, image gen, …) name the `invoke_rpc` method (`GenerateIconsAsset`, …) and confirm the downstream artifact logged under the **same** turn request ID unless evidence shows a child ID.

### Assets
| type | name | id |
|------|------|----|

### Caveats
<truncated dumps, inferred tools, ask_user ids that are not  request IDs>
```

Hand off:

```
/trace-request <requestId> <question>
```

---

## Known artifacts

| Artifact ID | Role |
|---|---|
| `surmap.onboard.session` | Streamed turns (`Start duplexer turn for session …`, `[invoke_rpc] request`) |
| `surmap.app.app-agent-codex` | Codex / skills |
| `surmap.www.app.agent.session-entry-service` | Persisted entries |
| `surmap.www.app.agent.session-event-service` | Persisted events |
| `surmap.www.app.agent.session-material-service` | Materials |
| `surmap.onboard.detection` | Icon generation (`IconsAssetService`) |
| `surmap.ds.-ai-gateway` / `google-ai-proxy` | Model calls |
| `surmap.onboard.session` | Credits / payments |
| `surmap.base_station.labelling` | Model log blobs |

Grafana fleet (not one conversation): [Agent - General](<service-url>) (`haq747c`), [Agent Codex](<service-url>) (`om8lskd`). BI cost: `events.dbo.sites_97` `evid=5000` `application_id='dd7678c5-39b3-443a-a385-a2cc494d977c'` with `sessionId=` in `additional_tags`.

Icon generation in-session is `invoke_rpc` → `.app.icons.v1.IconsAssetService` methods `EligibleForGeneration`, `CreateIconsAsset`, `GenerateIconsAsset`. Those typically **keep the turn request ID** on `onboard-detection-server`.

---

## Notes

- **Don't hunt for errors unless asked.** This skill reconstructs flow. Hand crashes to `/troubleshoot-request` and single-request "why" questions to `/trace-request`.
- **Slack is not a data source** for this command (search scopes are missing on the Slack MCP).
- **CLI timeout:** don't fire four `mcp-s` calls in parallel; two at a time is safer.
- **Widen the Grafana window with `updatedAt`**, not only the first turn — conversations pause on `ask_user` for hours.
