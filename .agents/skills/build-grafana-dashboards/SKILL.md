---
name: build-grafana-dashboards
description: Author and assemble Grafana dashboards as version-controlled, per-panel JSON files compiled by a build script into one importable dashboard. Covers the file-based layout, the assembly script, panel/variable anatomy, and the  data sources (Prometheus, Kubernetes, BI/Trino, app-logs/ClickHouse) with their query idioms. Use when creating or editing a service/business/log dashboard, or adding panels or sections.
---

> **Genericized import.** This workflow was originally written for a specific product and infrastructure. Service, artifact, dashboard and host names below are `example` placeholders — substitute SurMap's equivalents (see `README.md` and `docs/architecture.md`) before acting, and confirm any external system exists before calling it.


# Build Grafana Dashboards

Treat a Grafana dashboard as **source code**, not a blob exported from the UI. The
unit of editing is a single panel JSON file; a build script assembles the files in
deterministic order into one importable `dashboard.json`. This keeps diffs reviewable,
panels reusable, and ordering explicit.

All dashboards live at the **repo root** under `grafana/<dashboard-name>/` (one
directory per dashboard — they are **not** defined per package). A single repo-root
script, `scripts/build-grafana.mjs` (run via `uv run pytest -q`), discovers every
dashboard and assembles each into `tmp/<dashboard-name>-dashboard.json`.

The patterns below are **product-agnostic** — the examples (map, benefit programs,
asset lifecycle) are only illustrations. Apply the principles to any service, KPI,
or log dashboard.

```
grafana/
  <dashboard-name>/            ← one dashboard
    <dashboard-name>.md        ← dashboard reference doc (purpose, datasources, guidelines)
    dashboard.meta.json        ← title, uid, tags, time range, templating, annotations
    01-<section>/              ← section dirs, NN- prefix sets display order
      row.json                 ← the row panel (OPTIONAL — omit for flat dashboards)
      01-<panel>.json          ← panels, NN- prefix sets order within the section
      02-<panel>.json
    02-<section>/
      ...
  <another-dashboard>/         ← add more dashboards as sibling directories
    ...
```

Each dashboard directory self-documents in `grafana/<name>/<name>.md` (purpose,
data sources, variables, conventions, editing guidelines). **When invoked with a
dashboard reference** (e.g. `/build-grafana-dashboards <name>`), read
`grafana/<name>/<name>.md` first — it is the source of truth for that dashboard.
Keep the doc in sync with changes, and create one when adding a new dashboard.

## When to use

- Creating a new dashboard for a service, business KPI, or log-driven view.
- Adding/removing panels or sections, or reordering them.
- Editing queries, thresholds, or template variables.

## Core principles

1. **One directory = one dashboard.** Each dashboard is its own `grafana/<name>/`
   folder. Add a dashboard by adding a sibling folder; the build picks it up
   automatically. Dashboards are repo-root only — never per package.
2. **One file = one panel.** Never hand-maintain a monolithic dashboard JSON. Each
   panel is a standalone file; rows are their own files. The build script is the only
   thing that produces the combined document.
3. **Order is encoded in filenames.** Sections are `NN-<slug>/` directories; panels
   inside are `NN-<slug>.json`. Lexical sort = display order. To reorder, renumber.
4. **The meta file owns everything that isn't a panel** — title, uid, tags, time
   range, templating variables, annotations, schema version.
5. **Build output is generated, not edited.** `tmp/<name>-dashboard.json` (gitignored)
   is the artifact you import into Grafana; never edit it by hand.
6. **Datasources are referenced by uid**, and the uid must match the target Grafana.
   Use the canonical  uids documented in `references/datasources.md`.
7. **Round-trip discipline.** If someone edits in the Grafana UI, re-export and split
   the changes back into the per-panel files — don't let the UI become the source of
   truth. Bump `version` in the meta file when you do. The `/merge-grafana-dashboard
   <name>` command automates this reconciliation (fetch live via the `grafana` MCP →
   diff against the on-disk build → merge into the files → rebuild).

## Workflow

0. **Editing an existing dashboard?** Read `grafana/<name>/<name>.md` first — it
   documents that dashboard's purpose, variables, event/metric conventions, and
   editing guidelines. Keep the doc in sync with your changes.
1. **Pick the data source(s)** for what you're measuring, and read
   `references/datasources.md` for the query idiom + canonical uid:
   - Service health / RED metrics / infra → **Prometheus** (`000000452`)
   - Pod / autoscaler / container state → **Kubernetes** (`kube_*` on Prometheus)
   - Business KPIs / funnels / revenue → **BI** (`-trino-datasource`)
   - Structured app logs / request tracing → **app-logs** (ClickHouse)
   - For BI panels, **use the Quix MCP** (`quix__mutate_datadocs` →
     `quix__execute_query_cells` → `quix__get_executions`) to discover event names,
     evid values, and column shapes before encoding queries in panel JSON. See
     `references/datasources.md §3a`.
2. **Scaffold the layout** — a new `grafana/<dashboard-name>/` dir holding
   `dashboard.meta.json` + `NN-section/` dirs with a `row.json` each. See
   `references/build-script.md` for the exact directory contract.
3. **Author panels** one JSON file at a time. Copy the closest existing panel of the
   same type and adapt the `targets`/`title`/`gridPos`. See `references/panel-anatomy.md`.
4. **Define variables** in the meta file's `templating.list` so panels stay generic
   (`$service`, `$dc`, `$fleet`, …). See the Templating section of `panel-anatomy.md`.
5. **Build**: `python scripts/build-dashboard.py` to build a single board
   to `tmp/<name>-dashboard.json` (prints the path for a quick import), or
   `uv run pytest -q` (no arg) to build them all. Verify the printed
   panel/section counts.
6. **Validate** the generated JSON imports cleanly (Grafana → Import, or compare via
   the Grafana MCP `get_dashboard_*` tools against a target uid). See
   `references/build-script.md` for the round-trip flow.

## Reference files

- `references/build-script.md` — directory contract, the assembly script, the meta
  file, `package.json` wiring, round-tripping from the UI.
- `references/panel-anatomy.md` — panel JSON structure (gridPos, fieldConfig, options,
  targets), the panel types (row/stat/gauge/timeseries/table/text), and templating
  variables.
- `references/datasources.md` — the four data sources, their canonical uids, query
  languages,  metric/table conventions, and copy-ready example queries.

## JSON schema & IDE validation

### Two formats, one pipeline

Source files (`dashboard.meta.json`, per-panel `*.json`) use the **Grafana v12 classic
format** — human-friendly, numeric enums, flat `templating.list`. The build script
transforms them to the **Grafana v2 scenes format** (kind/spec, string enums) before
writing `tmp/*.json`. Never mix the two in the same file.

| File | Format | Validated by |
|------|--------|--------------|
| `grafana/**/dashboard.meta.json` | v12 authoring | suppressed (`.vscode/settings.json` overrides schema to permissive) |
| `tmp/*-dashboard.json` | v13 / v2 scenes | IDE JSON language server (full Grafana v2 schema) |

The `.vscode/settings.json` override for `dashboard.meta.json` is intentional — the
meta file uses v12 format and the IDE would otherwise flag every variable as malformed.

### Canonical schema location (grafana/grafana)

The source of truth for what fields are required in the built output:

```
apps/dashboard/kinds/
  v2/dashboard_spec.cue          ← CUE schema (authoritative)
  v2alpha1/dashboard_spec.cue

packages/grafana-schema/src/schema/dashboard/
  v2/dashboard.schema.json        ← schema (generated from CUE)
  v2alpha1/types.spec.gen.ts
  v2beta1/types.spec.gen.ts
```

When an IDE reports a missing or wrong property in the built JSON, look it up in
`types.spec.gen.ts` for the exact field name, type, and enum values.

### Known v12 → v13 enum conversions (implemented in `build-grafana.mjs`)

The build script maps numeric v12 values to the string enums the v13 schema requires:

**Variable `hide`** (`HIDE` map):

| v12 | v13 |
|-----|-----|
| `0` | `"dontHide"` |
| `1` | `"hideLabel"` |
| `2` | `"hideVariable"` |

**`QueryVariable.refresh`** (`REFRESH` map):

| v12 | v13 |
|-----|-----|
| `0` | `"never"` |
| `1` | `"onDashboardLoad"` |
| `2` | `"onTimeRangeChanged"` |

**`QueryVariable.sort`** (`SORT` map):

| v12 | v13 |
|-----|-----|
| `0` | `"disabled"` |
| `1` | `"alphabeticalAsc"` |
| `2` | `"alphabeticalDesc"` |
| `3` | `"numericalAsc"` |
| `4` | `"numericalDesc"` |

### Adding a new variable type to the build script

If you add a new variable `type` (e.g. `"textbox"`, `"interval"`, `"datasource"`),
add a branch in `transformVariables()` in `scripts/build-grafana.mjs` that emits the
correct v13 `kind` and `spec`. The fallback `return v` at the bottom only passes through
objects that are **already** in v13 `kind/spec` shape — a raw v12 variable object will
fail schema validation in the built output.

### Fixing new schema violations

1. Open `tmp/<name>-dashboard.json` in the IDE — the JSON language server highlights
   violations inline.
2. Match the error to a type in
   `packages/grafana-schema/src/schema/dashboard/v2/types.spec.gen.ts`
   (in the grafana/grafana repo).
3. Fix `build-grafana.mjs` — either add the missing field to the relevant
   `transform*` function, or add a new enum mapping. Rebuild and re-check.
4. Do **not** edit `tmp/*.json` directly — fix the transform, then rebuild.

## Guardrails

- **Don't** put product-specific identifiers in the build script — keep them in
  panel files / variables so the tooling stays reusable.
- **Don't** edit `tmp/*-dashboard.json` directly; regenerate it.
- **Do** keep `gridPos` coherent per section (x+w ≤ 24); the script preserves whatever
  you set, it does not auto-layout.
- **Do** parameterize every product/service name via a template variable or the meta
  file, never inline it across dozens of panels.
