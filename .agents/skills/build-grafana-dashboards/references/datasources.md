# Data sources & query idioms

Four data sources cover almost every  dashboard. Each panel/target references one by
`uid`. **The uids below are the canonical -internal ones, but always confirm against
the target Grafana** with the Grafana MCP `list_datasources` tool (uids differ per
instance and can change). All queries are **illustrative** — swap in your own
service/artifact/table.

| Purpose | Datasource | `type` | Canonical uid | Language |
|---------|-----------|--------|---------------|----------|
| Service metrics (RED, infra) | Prometheus | `prometheus` | `000000452` | PromQL |
| Pod / autoscaler / container | Kubernetes (kube-state + cAdvisor) | `prometheus` | `000000452` | PromQL |
| Business KPIs / funnels | BI (Trino) | `-trino-datasource` | `dfapzm9onuv40a` | Trino SQL |
| Structured app logs | app-logs | `grafana-clickhouse-datasource` | `f14e4dc2-fcce-4d7b-8d6e-884b90429729` | ClickHouse SQL |

Related ClickHouse sources you may also reference: `bi-events`
(`b324e168-2962-42e5-bfa7-b243d14a8424`), `observability` (`logs_db.observability`),
`domain-events`, `access-logs`.

> **Quix** is not a Grafana datasource — it is a notebook IDE over the same Trino
> warehouse used by the BI datasource. Use the Quix MCP to **explore and validate**
> queries interactively before putting them in panel JSON. See §3a for the workflow.

---

## 1. Prometheus — service & infra metrics

 exposes metrics in a `/metrics` endpoint with a consistent label schema. Metric
names are generic; the **`tag` label selects the family**, and `service`/`artifact_id`
scope to your app.

**Key metric names & labels**

| Metric | Meaning | Notable labels |
|--------|---------|----------------|
| `m1_rate` | 1-min rate of a counter (RPS) | `tag` (`RPC_SERVER`, `METER`), `service`, `dc`, `fleet`, `operation`/`method`/`class`, `error`, `status`, `source` |
| `hist` | Histogram quantile value | `quantile` (`0.5`/`0.95`/`0.99`), `tag`, `service`, `measure`, `operation` |
| `gauge` | Point-in-time value | `tag=INFRA`, `class` (`process`/`health`), `gauge` (e.g. `uptime-seconds`, `memory-rss-mb`, `cpu-permits-in-use`) |
| `envoy_cp_*` | LB/pod membership from Envoy control plane | `envoy_cp_total_count`, `envoy_cp_alive_count`; `tag=http`, `artifact_id`, `dc` |

**Conventions**

- `service` is usually a hidden **constant** variable holding the full artifact id
  (`surmap.onboard.capture`); queries filter `service="$service"` (or
  `artifact_id="$service"` for envoy/kube metrics).
- Multi-value DC/fleet vars use **regex match**: `dc=~"$dc"`, `fleet=~"$fleet"`.
- `error=""` selects successful requests; non-empty `error` = failures. `status="ok"`
  is the equivalent on `METER` meters.

**Examples**

```promql
# Throughput per DC (RPS), successes only
sum(m1_rate{tag="RPC_SERVER",service="$service",dc=~"$dc",fleet=~"$fleet",error=""}) by (dc)

# Uptime (minutes)
max(gauge{tag="INFRA",class="process",gauge="uptime-seconds",service="$service",dc=~"$dc"}) / 60

# Per-operation custom meter (request count by DC)
sum(m1_rate{tag="METER",source="my-operation",operation="${endpoint}",service="$service",status="ok"}) by (dc)

# Request-rate-weighted p50 latency per DC (combine hist quantile with m1_rate weight)
sum((max(hist{quantile="0.5",tag="RPC_SERVER",service="$service",dc=~"$dc"} > 0) by (class,method,dc))
    * (sum(m1_rate{tag="RPC_SERVER",service="$service",dc=~"$dc"}) by (class,method,dc))) by (dc)
  / sum(m1_rate{tag="RPC_SERVER",service="$service",dc=~"$dc"}) by (dc)
```

---

## 2. Kubernetes — pods, autoscaling, containers

Same Prometheus datasource; metrics come from kube-state-metrics (`kube_*`) and cAdvisor
(`container_*`). Scope by `dc` and the workload name (often `$app`/`$service`).

```promql
# HPA desired vs max replicas
max(kube_horizontalpodautoscaler_status_desired_replicas{dc="$dc",horizontalpodautoscaler="$app"})
max(kube_horizontalpodautoscaler_spec_max_replicas{dc="$dc",horizontalpodautoscaler="$app"})

# Alive vs total pods (Envoy control-plane view)
min(envoy_cp_alive_count{dc="$dc",tag="http",artifact_id="$service"})
max(envoy_cp_total_count{dc="$dc",tag="http",artifact_id="$service"}) default(0)

# Pods waiting by reason / container memory working set — typical kube_* / container_* metrics
sum(kube_pod_container_status_waiting_reason{...}) by (reason)
sum(container_memory_working_set_bytes{...}) by (pod)
```

Useful families: `kube_pod_status_phase`, `kube_pod_container_status_waiting_reason`,
`kube_pod_container_status_terminated_reason` (OOM), `container_cpu_usage_seconds_total`,
`container_cpu_cfs_throttled_*`, `container_memory_working_set_bytes`.

---

## 3. BI (Trino) — business KPIs and funnels

SQL over the BI event warehouse. Tables follow `events.dbo.<entity>_<NN>` (e.g.
`events.dbo.sites_97`, `events.dbo.users_193`), with an `evid` column selecting the
event type. Scope to a product via `artifact_name` or `application_id`.

**Grafana panel wiring**

The Grafana datasource type is `-trino-datasource` (uid `dfapzm9onuv40a`). The
target object uses `rawSQL` (**capital SQL** — not `rawSql`) and `format`:

```json
{
  "datasource": { "type": "-trino-datasource", "uid": "dfapzm9onuv40a" },
  "format": 0,
  "rawSQL": "SELECT ...",
  "refId": "A"
}
```

- `format: 0` — time series (first column must be a timestamp)
- `format: 1` — table / single-value stat

**Key BI event columns**

| Column | Notes |
|--------|-------|
| `artifact_name` | Product slug, e.g. `'mapping-pipeline'`, `'editor-app'` |
| `evid` | Event type (see known values below) |
| `action` | Action name, e.g. `'select_fill_pdf'`, `'fill_pdf'`, `'download'` |
| `action_result` | Outcome string, e.g. `'success'`, `'no_fields'`, `'fail'` |
| `action_type` | Intent, e.g. `'click'`, `'complete'` |
| `logged_user_id` | Use for distinct-user counts |
| `date_created` | Event timestamp — use with `$__timeFilter` |
| `src` | Source id (e.g. `193`) — safe to filter on per-table |

**Known evid values (src=193)**

| evid | Type | Fired by |
|------|------|---------|
| 24 | Feature/tool selected | `select_<tool>` / `deselect_<tool>` events — tool entry/exit |
| 25 | `ActionCompletedEvent` | Long operations: merge, split, convert, fill fields resolution |
| 27 | `PanelStateChangedEvent` | Click-level interactions: button clicks, file add, toggle, download |

**Watch out for cross-artifact funnels.** Not all steps of a user flow are reported
under the same `artifact_name`. For example, the semantic mapping pipeline fill form flow spans two
artifacts:

```
evid=24, artifact_name='mapping-pipeline', action='select_fill_pdf'   ← tool opened
evid=25, artifact_name='mapping-pipeline', action='fill_pdf'          ← fields resolved
evid=27, artifact_name='editor-app', action='download'         ← map exported
```

When a funnel step is in a different artifact, drop the `artifact_name` filter from
the `WHERE` clause and qualify each `CASE WHEN` branch with its own `artifact_name`.

**Query patterns**

```sql
-- Stat: count unique users who performed one action in the time range
SELECT count(distinct logged_user_id) AS "Label"
FROM events.dbo.users_193
WHERE artifact_name = 'my-product'
  AND evid = 25
  AND action = 'my_action'
  AND $__timeFilter(date_created)

-- Time series: daily unique users, all actions
SELECT date_trunc('day', date_created), udger_device_class,
       count(distinct logged_user_id) AS total
FROM events.dbo.users_193
WHERE $__timeFilter(date_created)
  AND artifact_name = 'my-product'
GROUP BY 1, 2
ORDER BY 1 ASC

-- Funnel time series: multiple steps on one chart (cross-artifact safe)
SELECT
  date_trunc('day', t.date_created) AS time,
  COUNT(DISTINCT CASE WHEN t.artifact_name = 'my-product' AND t.evid = 24
                       AND t.action = 'select_my_flow'   THEN t.logged_user_id END) AS "1. Opened",
  COUNT(DISTINCT CASE WHEN t.artifact_name = 'my-product' AND t.evid = 25
                       AND t.action = 'my_action'
                       AND t.action_result = 'success'   THEN t.logged_user_id END) AS "2. Completed",
  COUNT(DISTINCT CASE WHEN t.artifact_name = 'editor-app' AND t.evid = 27
                       AND t.action = 'download'         THEN t.logged_user_id END) AS "3. Exported"
FROM events.dbo.users_193 t
WHERE t.src = 193
  AND $__timeFilter(t.date_created)
GROUP BY 1
ORDER BY 1 ASC

-- Action totals (table)
SELECT action, count(distinct logged_user_id) AS unique_users, count(*) AS actions
FROM events.dbo.users_193
WHERE evid = 27 AND $__timeFilter(date_created) AND artifact_name = 'my-product'
GROUP BY 1 ORDER BY 2 DESC
```

---

## 3a. Quix — exploring BI data before writing panel queries

**Quix** is a notebook-style SQL IDE over the same Trino warehouse. Use it to
discover available events, check column names, and validate queries before encoding
them in panel JSON. It is available as an MCP server (`Quix` in `.mcp.json`).

**Workflow: explore → confirm → encode**

1. **Discover what events exist** for your product/flow:
   ```sql
   SELECT artifact_name, action, evid, action_result, count(*) AS cnt
   FROM events.dbo.users_193
   WHERE artifact_name LIKE '%my-product%'
     AND date_created >= DATE '2026-06-01'
   GROUP BY 1, 2, 3, 4
   ORDER BY cnt DESC
   LIMIT 50
   ```
2. **Confirm column names** with `SELECT * FROM events.dbo.users_193 LIMIT 1`.
3. **Prototype the funnel query** in a Quix DataDoc until the row counts look right.
4. **Copy the validated SQL into the panel JSON** `rawSQL` field.

**MCP tools**

| Tool | Use |
|------|-----|
| `quix__get_context` | Confirm who you're authenticated as |
| `quix__mutate_datadocs` | Create a DataDoc with initial cells |
| `quix__mutate_cells` | Insert / update query cells in an existing DataDoc |
| `quix__execute_query_cells` | Run cells and wait for terminal status |
| `quix__get_executions` | Fetch results (`view: "statement_results"`) |

**Creating a throwaway exploration DataDoc**

```json
// mutate_datadocs — create with an initial query cell
{
  "operations": [{
    "op": "create",
    "title": "Exploration scratchpad",
    "cells": [{
      "type": "query",
      "language": "trino_sql",
      "content": "SELECT action, evid, count(*) AS cnt FROM events.dbo.users_193 WHERE artifact_name = 'mapping-pipeline' AND date_created >= DATE '2026-06-01' GROUP BY 1, 2 ORDER BY cnt DESC LIMIT 20"
    }]
  }]
}
// returns datadoc_id and cell_id — use them with execute_query_cells
```

**Reading results**

```json
// get_executions
{ "query_execution_ids": <id>, "view": "statement_results", "result_limit": 100 }
// result.items[0].statement_executions[0].result.columns / .rows
```

**Quix UI link** — every DataDoc and cell returned by the MCP includes a `ui_link`
you can open in a browser to inspect results visually.

---

## 4. app-logs (ClickHouse) — structured logs & tracing

SQL over `logs_db.app_logs`. This is the source for request tracing, error breakdowns,
and lifecycle views. Scope by `artifact_id` (full `surmap.*`).

**Columns you'll use most**: `timestamp`, `level`, `request_id`, `message`, `data`
(JSON string), `artifact_id`, `transaction_name`, `dc`, `kind`, `error_class`,
`error_type`, `meta_site_id`, `caller`, `logger_name`, `stack_trace`, `pod_name`.

**Conventions**

- Time: `$__timeFilter(timestamp)`; bucket with `$__timeInterval(timestamp)`.
- Optional multi-select filter: `$__conditionalAll(level IN (${log_level:singlequote}), $log_level)`
  — applies the filter only when the var isn't "All".
- Entity search across `message`/`data`: `data LIKE '%$asset_id%' OR message LIKE '%$asset_id%'`.
- Prepend an attribution comment so queries are traceable in ClickHouse:
  `/* ${__dashboard} ${__user.email} */`.
- Related tables: `logs_db.app_logs_shard` (for heavy sub-queries / top-N),
  `logs_db.observability` (transaction/Observability events, keyed by `full_artifact_id`).

```sql
/* ${__dashboard} ${__user.email} */
-- Logs for a single request id, level-filtered
select timestamp, level, request_id, message, data
from logs_db.app_logs
where artifact_id = 'surmap.onboard.capture'
  and $__timeFilter(timestamp)
  and request_id = '$request_id'
  and $__conditionalAll(level IN (${log_level:singlequote}), $log_level)
order by timestamp

-- Error occurrence over time, limited to the top error classes
select $__timeInterval(timestamp) as t, count() as c, error_class
from logs_db.app_logs
where $__timeFilter(timestamp) and artifact_id = 'surmap.onboard.capture'
group by t, error_class order by t
```

---

## Picking a datasource

- **"Is the service healthy / fast / erroring?"** → Prometheus (RED + infra).
- **"How many pods / is it autoscaling / OOMing?"** → Kubernetes metrics (Prometheus).
- **"How many users / revenue / funnel conversion?"** → BI (Trino).
- **"What happened to this specific request / entity?"** → app-logs (ClickHouse).

Mixing is fine: a panel can target one datasource while another panel on the same
dashboard targets a different one. Set `datasource` per panel (and per target).
