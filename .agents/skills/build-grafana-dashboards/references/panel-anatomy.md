# Panel anatomy & templating

Every panel file is a standalone Grafana panel object. The fastest correct way to
author one is to **copy the closest existing panel of the same type** and adapt
`title`, `gridPos`, and `targets`. This page explains the parts so you can adapt
confidently. All examples are illustrative — datasource uids and metric names are
covered in `datasources.md`.

## The shared skeleton

```jsonc
{
  "datasource": { "type": "prometheus", "uid": "000000452" }, // panel-level default ds
  "fieldConfig": { "defaults": { /* units, thresholds, colors */ }, "overrides": [] },
  "gridPos": { "x": 0, "y": 0, "w": 8, "h": 8 },              // layout (see below)
  "id": 30,                                                    // unique within dashboard
  "options": { /* viz-type-specific display options */ },
  "pluginVersion": "12.2.8+security-01",
  "targets": [ { /* one query per target, refId A/B/C... */ } ],
  "title": "Throughput per DC (RPS)",
  "type": "timeseries"                                         // viz type
}
```

### `gridPos` — layout

Grafana's grid is **24 columns wide**; `h` is in row units (~30px). You place panels
manually:

- `x` + `w` must be ≤ 24 within a row band; wrap to the next `y` when full.
- Keep `y` increasing down the section. The build script does **not** auto-pack —
  whatever you write is what renders. A common bug is overlapping panels from a bad
  `y`/`h`; verify after import.
- Rows (`type: "row"`) are full width: `{ "h": 1, "w": 24, "x": 0, "y": N }`.

### `id`

Must be unique within the assembled dashboard. When adding panels, pick an id higher
than any existing one. Grafana also tolerates re-import without ids, but keeping them
stable makes diffs and deep-links predictable.

### `fieldConfig.defaults` — units, thresholds, color

- `unit`: `"s"` (seconds), `"ms"`, `"percent"` (0–100) vs `"percentunit"` (0–1),
  `"short"`, `"bytes"`, `"reqps"`, `"m"` (minutes), etc.
- `thresholds`: `{ "mode": "absolute", "steps": [ {color,value}, ... ] }` — drives
  stat/gauge coloring. First step is usually `value: null`/`0`.
- `min`/`max`, `decimals`, `mappings` (value→text), `color.mode`
  (`palette-classic` for series, `thresholds` for stat/gauge).
- `overrides`: per-series/field tweaks (e.g. color one legend entry red).

### `targets` — the queries

One object per query, each with a unique `refId` (`A`, `B`, …). Shape depends on the
datasource:

- **Prometheus** (`expr`, `legendFormat`, `range: true`, `editorMode: "code"`).
- **SQL-family** (ClickHouse/Trino: `rawSQL`/`query`, `format`, `refId`).

Always set the per-target `datasource` to match the panel (or a different ds for
mixed panels). See `datasources.md` for the query languages.

## Panel types (the working set)

| `type` | Use for | Key `options` |
|--------|---------|---------------|
| `row` | Section header / grouping. `collapsed` controls nesting (see build-script.md). | — |
| `stat` | Single big number (uptime, error %, current count). | `reduceOptions.calcs` (e.g. `["lastNotNull"]`), `colorMode`, `graphMode` |
| `gauge` | Value against thresholds (success rate, latency budget). | `reduceOptions`, `showThresholdLabels` |
| `timeseries` | Trends over time (RPS, latency, memory). | `legend` (`calcs`, `placement`), `tooltip.mode` |
| `table` | Per-row breakdowns, log rows, top-N. | `cellHeight`, field `overrides`, transformations |
| `bargauge` | Compare discrete categories (versions, per-pod). | `displayMode`, `orientation` |
| `piechart` | Share of a whole (calls by caller/protocol). | `pieType`, `legend` |
| `text` | Markdown notes / section descriptions. | `content`, `mode` |

### `row.json`

The section header. Non-collapsed example:

```jsonc
{ "collapsed": false, "gridPos": { "h": 1, "w": 24, "x": 0, "y": 0 }, "id": 2,
  "title": "Overview", "type": "row" }
```

Set `"collapsed": true` to make the section start collapsed; the build then nests the
section's panels inside the row (the panels still live as separate files).

## Panel repeat — dynamic rows from a variable

The **panel repeat** feature lets one panel file generate N panels at runtime (one per
variable value), avoiding a static explosion of nearly-identical files.

### How it works

Add two fields to the panel JSON:

```jsonc
{
  "repeat": "transaction",     // variable name (no $ prefix)
  "repeatDirection": "v",      // "v" = vertical (one row per value), "h" = horizontal
  ...
}
```

With `repeatDirection: "v"`, Grafana clones the panel once for each selected value of
`$transaction`, stacking them vertically. All clones share the same query template — the
variable substitution (`${transaction}`) resolves to each value independently.

To get a grid (e.g. 4 columns × N rows), place 4 panels side-by-side in a **collapsed
row** section, each with `"repeat": "transaction"`. Grafana expands each panel
independently, producing one visual row per variable value with all 4 panels visible.

### Variable setup

The variable must be **multi-valued** and have `includeAll: true` so that "All" selects
every value. By default, Grafana shows all 25 panels when `$__all` is chosen.

Use a **custom** variable for a fixed list (controls order explicitly, `sort: 0` preserves
list order):

```jsonc
{
  "name": "transaction",
  "type": "custom",
  "label": "Transaction",
  "hide": 2,
  "includeAll": true,
  "multi": true,
  "sort": 0,
  "current": { "selected": false, "text": "All", "value": "$__all" },
  "options": [],
  "query": "value-a,value-b,value-c"
}
```

Use a **query** variable (ClickHouse/Prometheus) for a dynamic list:

```jsonc
{
  "name": "endpoint",
  "type": "query",
  "datasource": { "type": "prometheus", "uid": "000000452" },
  "definition": "label_values(m1_rate{tag=\"RPC_SERVER\"}, transaction)",
  "query": { "qryType": 1, "refId": "A",
             "query": "label_values(m1_rate{tag=\"RPC_SERVER\"}, transaction)" },
  "includeAll": true, "multi": true, "refresh": 2, "sort": 1
}
```

### Ordering

For a **custom** variable: values appear in the order listed in `query`. Set `sort: 0` to
disable alphabetical sorting. Reorder by editing the `query` string.

For a **query** variable: `sort: 1` sorts alphabetically; `sort: 0` uses datasource order.
There is no UI control for repeat-panel order beyond the variable's sort setting.

### Collapsed row + repeat

Put the repeating panels inside a collapsed row section to keep the dashboard compact by
default. Only the row header is visible until expanded, at which point Grafana renders all
N × M panels.

```jsonc
// row.json — the section header
{ "collapsed": true, "gridPos": { "h": 1, "w": 24, "x": 0, "y": 34 },
  "id": 33, "title": "Transaction Trends", "type": "row" }

// 01-all.json — panel that repeats for each $transaction value
{
  "repeat": "transaction",
  "repeatDirection": "v",
  "gridPos": { "h": 8, "w": 6, "x": 0, "y": 35 },
  "title": "${transaction} — All",
  ...
}
```

### Title interpolation

Panel titles can include the variable: `"${transaction} — Desktop"`. In `"v"` mode,
each clone updates its title with the bound value, giving every row a meaningful header.

## Templating variables

Variables live in `dashboard.meta.json` under `templating.list` and keep panels
generic — panels reference `$var` / `${var}` / `${var:text}` instead of hardcoding
values. Refresh `2` = "on time range change".

### Common variable kinds

**Constant** (hidden config, e.g. the service id every query filters on):

```jsonc
{ "name": "service", "type": "constant", "label": "service",
  "query": "surmap.onboard.capture", "hide": 2 }
```

**Query** (options fetched from a datasource — the canonical  idiom uses
`label_values`):

```jsonc
{ "name": "dc", "type": "query", "label": "DC",
  "datasource": { "type": "prometheus", "uid": "000000452" },
  "definition": "label_values(envoy_cp_total_count{tag=\"http\",artifact_id=\"$service\"},dc)",
  "query": { "qryType": 1, "refId": "A",
             "query": "label_values(envoy_cp_total_count{tag=\"http\",artifact_id=\"$service\"},dc)" },
  "includeAll": true, "allValue": ".*", "multi": true, "refresh": 2 }
```

**Textbox** (free-text filter, e.g. an entity id to trace):

```jsonc
{ "name": "asset_id", "type": "textbox", "label": "Asset ID" }
```

### Using variables in queries

- **Multi-value + "All"**: pair `includeAll: true` + `allValue: ".*"` with a **regex
  match** in the query: `dc=~"$dc"` (not `dc="$dc"`). Single-value vars use `=`.
- **Chaining**: one variable's `definition` can reference another (`$service` inside
  the `dc` query above) → dependent dropdowns.
- **Formatting**: `${var:text}` (display label), `${var:singlequote}` (SQL `IN` lists),
  `${var}` (raw). For SQL, ClickHouse/Trino expose `$__timeFilter()`,
  `$__timeInterval()`, and `$__conditionalAll()` — see `datasources.md`.
- **Panel titles** can interpolate too: `"${endpoint:text} — Throughput"`.
