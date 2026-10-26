---
name: troubleshoot-request
description: Investigate a production failure given a Request ID. Fetches app logs and error stack traces from Grafana, identifies the deployed version at the time of the request, checks out the code at that git tag, and correlates the stack trace to actual source lines. Use when the user provides a Request ID and wants to understand what failed and why.
user-invocable: true
allowed-tools: Shell
---

> **Genericized import.** This workflow was originally written for a specific product and infrastructure. Service, artifact, dashboard and host names below are `example` placeholders — substitute SurMap's equivalents (see `README.md` and `docs/architecture.md`) before acting, and confirm any external system exists before calling it.


# Troubleshoot Request

End-to-end failure investigation for a Request ID: logs → stack trace → deployed version → code at that version.

## Invocation

```
/troubleshoot-request <requestId>
```

`$ARGUMENTS` is the Request ID. Example: `1774524481.7344535583129`

---

## Phase 1 — Extract Time Window

 Request IDs encode a Unix timestamp as the integer part before the first dot.

Run this shell block to derive the time window deterministically:

```bash
REQUEST_ID="$ARGUMENTS"
EPOCH=${REQUEST_ID%%.*}
FROM_S=$((EPOCH - 300))
TO_S=$((EPOCH + 300))
FROM_MS=$(( FROM_S * 1000 ))
TO_MS=$(( TO_S * 1000 ))

epoch_to_iso() { date -u -d "@$1" '+%Y-%m-%dT%H:%M:%S.000Z' 2>/dev/null || date -u -r "$1" '+%Y-%m-%dT%H:%M:%S.000Z'; }

NOW=$(date -u +%s)
AGE_S=$(( NOW - EPOCH ))
AGE_MIN=$(( AGE_S / 60 ))

echo "requestId: $REQUEST_ID"
echo "epoch:     $EPOCH"
echo "utc:       $(epoch_to_iso $EPOCH)"
echo "age:       ${AGE_MIN} minutes ago (${AGE_S}s)"
echo "from_iso:  $(epoch_to_iso $FROM_S)"
echo "to_iso:    $(epoch_to_iso $TO_S)"
echo "from_ms:   $FROM_MS"
echo "to_ms:     $TO_MS"
```

Report the derived UTC timestamp and ±5 min window to the user before querying.

---

## Phase 2 — Fetch Logs via grafana-datasource CLI

Use `@mcp-s/cli` to query **ClickHouse-backed** app logs and access logs. These have much longer retention than Loki (days, not hours). Requires auth — run `npx --registry "<service-url>" @mcp-s/cli@0.0.21 check-auth` first; if exit code is 4, run `login`.

**2a. Get time window** (replaces Phase 1 shell script):

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call grafana-datasource__get_request_id_time_window \
  '{"requestId": "<requestId>"}'
```

Returns `fromTime`, `toTime` (epoch−5min to epoch+10min window). Use these in all subsequent calls.

**2b. Query app logs** — primary source, search by request ID:

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call grafana-datasource__query_app_logs '{
    "sql": "SELECT timestamp, artifact_id, level, message, caller, error_class, stack_trace, data FROM app_logs WHERE $__timeFilter(timestamp) AND request_id = '\''<requestId>'\'' LIMIT 50",
    "fromTime": "<fromTime>",
    "toTime": "<toTime>"
  }'
```

**2c. Fetch error details** — after finding ERROR rows, re-query for their `data` JSON field (contains `errorMessage`, `resolvedPath`, `errorCode`):

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call grafana-datasource__query_app_logs '{
    "sql": "SELECT timestamp, message, data, stack_trace, error_class FROM app_logs WHERE $__timeFilter(timestamp) AND request_id = '\''<requestId>'\'' AND artifact_id = '\''<artifact_id>'\'' AND level = '\''ERROR'\'' LIMIT 10",
    "fromTime": "<fromTime>",
    "toTime": "<toTime>"
  }'
```

**2d. Query access logs** — for the originating URL, referer, and HTTP status. Always include `nginx_artifact_name` filter and use a tight ±2 min window; without these the query will time out. Use correct column names: `nginx_http_referer` and `nginx_http_user_agent` (not `nginx_referer`/`nginx_user_agent`):

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call grafana-datasource__query_access_logs '{
    "sql": "SELECT timestamp, nginx_artifact_name, nginx_request_method, nginx_request_uri, http_status_code, request_time, nginx_http_referer, nginx_http_user_agent FROM nginx WHERE $__timeFilter(timestamp) AND request_id = '\''<requestId>'\'' AND nginx_artifact_name = '\''<artifact_id>'\'' LIMIT 20",
    "fromTime": "<epoch-2min>",
    "toTime": "<epoch+2min>"
  }'
```

Report the `nginx_request_uri` (the path hit), `nginx_http_referer` (the page the user was on), and `nginx_http_user_agent`. This identifies where in the UI the failure was triggered. If `nginx_http_referer` is absent on the first hit, check the second entry — the gateway-proxied hop typically carries the referer.

**If zero results:** the request ID may not have reached any server-side service (browser-only, pre-boundary failure, or test ID). Report clearly and stop — do not guess.

### This repo's known artifacts (for label filtering)

| Artifact ID | Service |
|---|---|
| `surmap.base_station.segmentation` | gRPC map server |
| `surmap.base_station.mapping` | Browser semantic mapping pipeline (static) |
| `surmap.base_station.reconstruction` | map compute worker |
| `surmap.base_station.map_export` | Print preview viewer |
| `surmap.onboard.detection` | Icons generation server |
| `surmap.gotenberg-convert-server` | Document conversion server |

---

## Phase 3 — Extract Stack Traces and Version

From the Grafana results:

1. **Collect all error messages and stack trace lines.** Look for fields like `message`, `error`, `stack`, `exception`, `stacktrace`.

2. **Identify the artifact and version.** Look for:
   - A `version` or `app_version` field in log entries
   - The `artifact_id` label on matching log streams
   - Deployment events near the request time (see Phase 4 fallback below)

3. **Map service name → git tag format:**

   ```
   surmap.base_station.segmentation  →  surmap.base_station.mapping@<version>
   surmap.base_station.reconstruction  →  surmap.base_station.reconstruction@<version>
   surmap.base_station.map_export  →  surmap.base_station.map_export@<version>
   ```

   Verify the tag exists:
   ```bash
   git tag --list "surmap.base_station.mapping@<version>"
   ```

4. **Fallback — find deployed version from Captain's Logs** (if version not in log entries):

   Call `query_loki_logs` or use the Grafana datasource to query `captains_log`:
   ```sql
   SELECT event_time, action, artifact, description, additionalData
   FROM captains_log
   WHERE $__timeFilter(event_time)
     AND artifact ILIKE '%mapping-pipeline%'
     AND origin = 'DeploymentPlatform'
   ORDER BY event_time DESC
   LIMIT 20
   ```
   Use a window of 2 hours before the request time to catch the most recent deployment.

   Parse the version from the deployment entry's `additionalData` or `description`.

---

## Phase 4 — Look Up Code at That Version

Once you have the git tag, read the relevant source files.

**List files changed in that tag vs its predecessor:**
```bash
git log --oneline <tag> -1
# find the commit behind that tag:
PREV_TAG=$(git tag --sort=-version:refname | grep "^surmap.base_station.mapping@" | awk 'NR==2')
git diff --name-only $PREV_TAG <tag>
```

**Read a specific file at the tag:**
```bash
git show <tag>:mapping-pipeline/mapping-pipeline-server/src/handlers/foo.ts
```

**Match stack trace frames to source files:**

For each frame in the stack trace of the form `at Foo (/app/src/handlers/bar.js:42:10)`:
1. Strip the `/app/src/` prefix and `.js` extension → `mapping-pipeline/mapping-pipeline-server/src/handlers/bar.ts`
2. Read the file at the tag: `git show <tag>:mapping-pipeline/mapping-pipeline-server/src/handlers/bar.ts`
3. Show the failing line with ±10 lines of context (using `sed -n '32,52p'` on the fetched content)

If the stack trace references the native RTAB-Map binding or a stub, map it back to the adapter in `src/surmap/slam/rtabmap.py` by matching function names.

---

## Phase 5 — Synthesize

Present a concise failure report:

```markdown
## Request Failure Analysis

**Request ID:** `<id>`
**UTC time:** <timestamp>
**Service:** <artifact-id> @ v<version>
**Git tag:** `<tag>`

### Error

<error message>

### Stack Trace (top 3 frames)

| Frame | File | Line |
|---|---|---|
| <function> | <file> | <line> |
| ... | ... | ... |

### Failing Code (v<version>)

```<language>
// mapping-pipeline/mapping-pipeline-server/src/handlers/foo.ts:<line>
<code context ±10 lines, failing line highlighted with // ← ERROR>
```

### Likely Cause

<1–3 sentences: what the code was doing, what condition was unhandled, what the log message indicates>

### Suggested Next Steps

- [ ] Check if v<next-version> already fixes this
- [ ] Reproduce with: <minimal repro hint from logs>
- [ ] Related PR / commit: `git log --oneline <prev-tag>..<tag>`
```

---

## Notes

- **Expand the window if needed.** For long-running requests or worker jobs, widen Phase 1 to −2 min / +11 min by replacing `300` with `120` (from) and `660` (to).
- **The Grafana MCP is already connected** in this project — no auth setup needed. If tools fail, verify with `mcp__Grafana__grafana-mcp__list_datasources`.
- **Primary log source is ClickHouse** via `grafana-datasource__query_app_logs` — much longer retention than Loki. Loki (~4–5h) is a fallback only.
- **`@mcp-s/cli` auth:** token expires in ~24h. If `check-auth` returns exit 4, run `login` (requires browser).
- **Base-station side only.** This skill focuses on base-station errors. On-board `surmap` (CM5) errors before session ingest won't appear in the base station's logs — check the session log recorded on the CM5 instead.
- **WASM stack traces** from `stereo-ingest` or `reconstruction-services` will show Rust function names — map them to `mapping-pipeline/stereo-ingest/src/` or `mapping-pipeline/reconstruction-services/src/` and use `git show <tag>:<path>`.
