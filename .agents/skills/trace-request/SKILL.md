---
name: trace-request
description: Trace and explain the full flow of a Request ID. Fetches the complete (non-error) log/event timeline from Grafana across all services, reconstructs the request flow including async Kafka/Greyhound hops and experiment conductions, matches each pivotal log line to the emitting code at the deployed version, and answers a free-form question or analysis task about what the request did or did not do. Also detects blind spots — branches, decisions, and async jobs that produced no logs — and recommends concrete logging/metric/BI improvements. Use when the user gives a Request ID plus a question ("why did X happen", "did Y trigger", "trace this request") rather than a crash to debug.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob, Agent
---

> **Genericized import.** This workflow was originally written for a specific product and infrastructure. Service, artifact, dashboard and host names below are `example` placeholders — substitute SurMap's equivalents (see `README.md` and `docs/architecture.md`) before acting, and confirm any external system exists before calling it.


# Trace Request

Peer of `troubleshoot-request`. That skill hunts an error and maps the stack trace to a crash. **This skill assumes nothing failed** — it reconstructs the *flow* of a request, aligns it with the code that produced it, answers the user's question, and reports where the trace went dark.

## Invocation

```
/trace-request <requestId> <question / analysis task>
```

`$ARGUMENTS` is a Request ID **followed by a free-form question**. Split on the first whitespace after the request ID.

Example: `1781850834.12615161848511336 why did image prerendering not trigger?`

The request ID is the first whitespace-delimited token; everything after it is the question. If no question is given, default to "reconstruct and explain what this request did."

---

## Phase 0 — Parse the invocation

Extract `REQUEST_ID` (first token) and `QUESTION` (the rest). State both back to the user, then derive the time window:

```bash
REQUEST_ID="$(echo "$ARGUMENTS" | awk '{print $1}')"
QUESTION="$(echo "$ARGUMENTS" | cut -d' ' -f2-)"
EPOCH=${REQUEST_ID%%.*}
epoch_to_iso() { date -u -d "@$1" '+%Y-%m-%dT%H:%M:%S.000Z' 2>/dev/null || date -u -r "$1" '+%Y-%m-%dT%H:%M:%S.000Z'; }
echo "requestId: $REQUEST_ID"
echo "question:  $QUESTION"
echo "utc:       $(epoch_to_iso $EPOCH)"
echo "from_iso:  $(epoch_to_iso $((EPOCH-300)))"
echo "to_iso:    $(epoch_to_iso $((EPOCH+600)))"
```

Report the derived UTC time and the −5 min / +10 min window before querying. Async flows (Kafka consumers, worker jobs) often land *after* the synchronous request, so the window deliberately leans forward.

---

## Phase 1 — Auth

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 check-auth
```

Exit 0 = good. Exit 4 = run `login` (requires browser). Token lasts ~24h.

> **Time-format gotcha (learned the hard way):** `query_app_logs` / `query_access_logs` reject bare epoch-millis strings — *"no timezone designator"*. **Always pass ISO-8601 with a `Z`** (e.g. `2026-06-19T06:28:54Z`). The `get_req_id_window` tool name in some deployments is `get_request_id_time_window` and may 404 — if it does, just compute the window yourself in Phase 0 and pass ISO strings.

---

## Phase 2 — Fetch the *whole* flow (not just errors)

The defining difference from `troubleshoot-request`: **do not filter by `level = ERROR`.** Pull every log line for the request across every service, ordered by time. Use ClickHouse (`query_app_logs`) — long retention, all artifacts.

**2a. Full timeline, all artifacts.** Note `build_version` does **not** exist in `app_logs` — don't select it.

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call grafana-datasource__query_app_logs '{
    "sql": "SELECT timestamp, artifact_id, level, message, caller, data FROM app_logs WHERE $__timeFilter(timestamp) AND request_id = '\''<requestId>'\'' ORDER BY timestamp LIMIT 300",
    "fromTime": "<from_iso>",
    "toTime": "<to_iso>"
  }'
```

**Outputs are large — persist and parse, never eyeball raw.** The CLI auto-saves big results to a file path; otherwise pipe through Python. A reusable parser:

```bash
# Summarize distribution, then walk one service's flow with decoded `data`
python3 - "$RESULT_FILE" <<'PY'
import json, sys
raw = open(sys.argv[1]).read()
obj = json.loads(raw)
inner = json.loads(obj["content"][0]["text"]) if "content" in obj else obj
logs = inner["logs"]
from collections import Counter
print("by artifact:", Counter(l["artifact_id"].split('.')[-1] for l in logs))
print("by level:", Counter(l["level"] for l in logs))
for l in logs:
    d = l.get("data") or ""
    print(f'{l["timestamp"]} {l["artifact_id"].split(".")[-1]:24} {l["level"]:5} {l["message"][:90]} | {d[:200]}')
PY
```

**2b. Drill into the service(s) that matter for the question** — raise the limit and read full `data` JSON. The `data` field carries the decision-relevant payload (entity IDs, counts, flags, phase markers, Kafka topics/offsets). Decode it:

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call grafana-datasource__query_app_logs '{
    "sql": "SELECT timestamp, level, message, data FROM app_logs WHERE $__timeFilter(timestamp) AND request_id = '\''<requestId>'\'' AND artifact_id = '\''<artifact_id>'\'' ORDER BY timestamp LIMIT 200",
    "fromTime": "<from_iso>", "toTime": "<to_iso>"
  }'
```

**2c. Experiment conductions** — feature flags often *are* the answer to "why did/didn't X happen". They are emitted by the conductor service:

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call grafana-datasource__query_app_logs '{
    "sql": "SELECT message FROM app_logs WHERE $__timeFilter(timestamp) AND request_id = '\''<requestId>'\'' AND artifact_id = '\''surmap.base_station.labelling'\'' LIMIT 100",
    "fromTime": "<from_iso>", "toTime": "<to_iso>"
  }'
```

Parse `Experiment ID` / `Conduction Status` (`SuccessfulConductionResult` vs `DidNotFindEligibleFilter` vs `MissingSeed`). **Caveat:** mapping-pipeline *Petri specs* conducted in-process (server handler `conductPetriBooleanExperiment`, or client `useExperiments`) usually do **not** appear here — their effect must be inferred from which code branch the logs show was taken (Phase 4).

**2d. Access logs (optional)** — the originating URL/referer. Tight ±2 min window + `nginx_artifact_name` filter or it times out. Columns: `nginx_http_referer`, `nginx_http_user_agent`.

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call grafana-datasource__query_access_logs '{
    "sql": "SELECT timestamp, nginx_artifact_name, nginx_request_method, nginx_request_uri, http_status_code, nginx_http_referer FROM nginx WHERE $__timeFilter(timestamp) AND request_id = '\''<requestId>'\'' AND nginx_artifact_name = '\''<artifact_id>'\'' LIMIT 20",
    "fromTime": "<epoch-2min ISO>", "toTime": "<epoch+2min ISO>"
  }'
```

**2e. Other event surfaces** (use when the flow points at them):
- `query_domain_events` — domain event bus (`surmap.v1.object` etc.)
- `query_bi_events` — product BI funnel events
- `query_loki` — fallback / short-retention raw logs

**If zero results:** the ID never reached the base station (on-board-only flow, pre-ingest, or a test ID). Say so and stop — on-board activity before ingest won't be here (the session log on the CM5 instead).

### Known artifacts (this repo)

| Artifact ID | Service |
|---|---|
| `surmap.base_station.segmentation` | gRPC map server |
| `surmap.base_station.mapping` | Browser semantic mapping pipeline (static) |
| `surmap.base_station.reconstruction` | map compute worker (Rust render) |
| `surmap.base_station.map_export` | Print preview viewer |
| `surmap.onboard.detection` | Icons generation server |
| `surmap.gotenberg-convert-server` | Document conversion server |
| `surmap.base_station.labelling` | Experiment conductor |

---

## Phase 3 — Reconstruct the flow

Turn the raw rows into a **causal timeline**, not a log dump. For each step capture: time (Δ from request start), service, what happened, and the payload that matters. Make the async hops explicit — they are the part people lose track of:

- **Sync span:** the gRPC handler that the request entered.
- **Produced events:** `Single message produced` / `Produced … jobs` rows reveal message topics (`surmap-object-creation-job`, `domain_events_example.surmap.v1.object`, `map-layer-update`…). These are fan-out points.
- **Consumed events:** `Node:GreyhoundClientInvocation` rows (with `groupId`, `topic`, `offset`, `durationMs`) are the consumer side picking those jobs back up — often the work the question is about.
- **Phase markers / decision payloads:** `data` fields like `phase`, `shouldX`, counts, `chunkType`, branch-revealing flags.

Render it as a compact table or sequence list. Mark the spot in the flow that the question is really about.

---

## Phase 4 — Match the flow to the code (the core technique)

This is how you answer *why*. For each pivotal log line — especially a branch decision or a step that's missing — find the exact code that emits it at the **deployed version**, and read the surrounding gate.

1. **Get the deployed version & tag.** Map service → tag and pick the version live at request time (recent request ≈ latest tag; otherwise confirm via `captains_log`, 2h lookback). Verify the change you care about is in it:
   ```bash
   git tag --sort=-version:refname | grep "^surmap.base_station.segmentation@" | head -3
   git merge-base --is-ancestor <commit> surmap.base_station.segmentation@<version> && echo "in tag"
   ```

2. **Grep the log message back to its call site.** A distinctive message string is a near-unique anchor:
   ```bash
   git show <tag>:mapping-pipeline/mapping-pipeline-server/src/handlers/Foo.ts | grep -n "Processing subasset creation batch"
   # or search the tree
   grep -rn "Processing subasset creation batch" {common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/src
   ```

3. **Read the branch.** Pull the function and identify **which branch the logs prove was taken** vs the branch that's silent. The presence of message A and the *absence* of message B is itself evidence — e.g. seeing `getAllPageDimensionsFromSource` + `bulkCreateAssetsRealtime` but **not** `Resolved render output paths` pins the `if (skipPrerender)` branch, which in turn reveals the spec value without it ever being logged.

4. **Trace the gate to its input.** When a branch hinges on `conductPetriBooleanExperiment(... SOME_SPEC ...)` or a config flag, name the spec/flag and state its inferred value. That inferred flag value is usually the real answer.

5. **Confirm entity state** when relevant — re-query an asset's `externalConfig` (or the domain entity) to confirm a field the code reads (e.g. a missing `prerenderedImagePath`) actually is/isn't present.

When the matching spans many files, delegate the search to an `Explore` agent with the concrete anchors (message strings, flag names, file hints) and ask it to quote the decisive gate with `file:line`.

---

## Phase 5 — Answer the question

Lead with a direct answer, grounded in flow + code:

```markdown
## Request Trace — <requestId>
**UTC:** <ts> · **Question:** <question>
**Service(s):** <artifact> @ v<version>

### Answer
<1–3 sentences answering the question directly. If it's "why didn't X happen",
name the branch taken and the flag/condition that steered it.>

### Flow
| Δt | Service | Step | Key data |
|----|---------|------|----------|
| +0ms | mapping-pipeline-server | <gRPC entry> | … |
| +Nms | …(Kafka topic) | produced/consumed | … |

### Evidence (code at v<version>)
- `<log message>` → `packages/…/Foo.ts:<line>` — <which branch / gate>, quoted.
- Branch **not** taken: `<absent message>` → confirms <inference>.

### Caveats
<assumptions, inferred-not-logged flag values, anything the data couldn't confirm>
```

---

## Phase 6 — Visibility gaps (always include)

The flow you reconstructed will have **dark stretches** — places you had to *infer* because nothing was logged. Call them out and propose concrete, minimal instrumentation. This is a first-class deliverable, not an afterthought.

Look for:

- **Silent branches** — an `if/else` where only one side logs, so the taken branch is ambiguous. *Fix:* one `log.info` at the top of each branch naming the decision (and the flag value that drove it).
- **Unlogged decision inputs** — a Petri spec / config flag that changed behavior but was never emitted. *Fix:* log the conducted value (`log.info('prerender gate', { spec, value })`) so future traces don't require code archaeology.
- **Fire-and-forget async** — a job produced to Kafka with no corresponding "completed/failed" log on the consumer, or a worker (`reconstruction-services`) that logs "stream started" but never "stream finished / N pages rendered". *Fix:* bracket the operation with start+outcome logs sharing the entity id; add a duration metric.
- **Missing correlation** — downstream/worker logs that don't carry the originating `request_id` or a stable entity id, so the trace can't be stitched. *Fix:* propagate the id into the async context and the log `data`.
- **No metric for the outcome** — the question ("did prerender trigger?") could be a counter. *Fix:* suggest a counter/gauge (e.g. `app_map_prerender_path_total{branch="skip|render"}`) so it's answerable without log spelunking.

For each gap, give: **what's dark → file:line where the log/metric should go → the exact line to add**, following `surmap` conventions (see `docs/architecture.md`). Present as a short checklist the user can act on.

---

## Notes

- **Don't go hunting for errors.** If you do spot an ERROR, mention it, but the job is explaining flow and answering the question, not crash forensics — hand off to `/troubleshoot-request` for that.
- **Absence is evidence.** A step that *should* have logged and didn't is often the whole answer. Treat the gap between expected and observed log lines as a primary signal.
- **Infer flags from branches, then say you inferred it.** In-process Petri specs rarely log; the code path proves the value. Always label inferred values as inferred in the Caveats.
- **Persist-and-parse.** Full-flow queries return tens of KB; save to a file and parse with Python rather than truncating in-terminal.
- **Widen forward, not back.** Worker/Kafka consumers land after the sync request — extend `to_iso` (+11/+15 min) before extending backward.
