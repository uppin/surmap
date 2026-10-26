# Build script & directory contract

A single repo-root script, `scripts/build-grafana.mjs`, run via `uv run pytest -q`:

- **`python scripts/build-dashboard.py`** — builds a **single** dashboard
  to `tmp/<dashboard-name>-dashboard.json` and prints the path, for a quick
  "copy JSON → Grafana → Import" round-trip. (A bare `<dashboard-name>` also works.)
- **`uv run pytest -q`** (no arg) — builds **every** dashboard under `grafana/`
  to `tmp/<dashboard-name>-dashboard.json`.

Run with an unknown name to list the available dashboards.

## Directory contract

```
grafana/
  <dashboard-name>/                 ← a "dashboard" = any dir with dashboard.meta.json
    dashboard.meta.json             ← required; everything that is not a panel
    NN-<slug>/                      ← a "section"; must match /^\d+-.+/
      row.json                      ← OPTIONAL; the Grafana row panel for the section
      NN-<slug>.json                ← panel files; must start with a digit (/^\d+/)
      NN-<slug>.json
    NN-<slug>/
      ...
```

Rules the script enforces (mirror them when authoring):

- A **dashboard** is any direct child directory of `grafana/` containing
  `dashboard.meta.json`. Anything else under `grafana/` is ignored.
- A **section** directory must be named `NN-<slug>/` (e.g. `01-overview/`,
  `07-errors/`). Sections are sorted by directory name → display order top-to-bottom.
- Inside a section, every `*.json` whose name starts with a digit is a **panel**,
  sorted by filename. `row.json` is special — it is the section's row header, not a
  panel.
- `row.json` is **optional**. A section without one just contributes its panels at the
  top level (no row header). Use this for **flat dashboards** that have no rows — make
  one section dir (e.g. `01-panels/`) holding only panel files. (The two imported
  dashboards `mapping-pipeline-business-kpis/` and `asset-lifecycle/` are flat examples.)
- The output filename is the dashboard directory's name: `tmp/<name>-dashboard.json`.

## How assembly works

For each dashboard:

1. Read `dashboard.meta.json` → this becomes the dashboard object minus `panels`.
2. For each section dir (sorted): read `row.json`, then each panel file (sorted).
3. Emit panels based on the row:
   - **no `row.json`** → emit the panels directly at the top level (flat dashboard).
   - **`"collapsed": true`** → panels are nested inside the row's `panels` array
     (`{ ...row, panels: [...] }`). This matches how Grafana stores a collapsed row.
   - **`"collapsed": false`** → emit the row first with an empty `panels: []`, then
     emit each panel at the top level.
4. `dashboard = { ...meta, panels: assembledPanels }` → written pretty-printed.

The script does **no layout math** — it preserves whatever `gridPos` you set in each
panel file. You own x/y/w/h coherence (see `panel-anatomy.md`).

## Adding a new dashboard

1. `mkdir grafana/<dashboard-name>/`
2. Add `dashboard.meta.json` (copy an existing one; change `title`, `uid`, `tags`,
   `templating`, `time`). The `uid` must be unique and match the dashboard in Grafana.
3. Add `NN-<section>/` dirs, each with numbered panel files (and a `row.json` if the
   dashboard has rows).
4. `python scripts/build-dashboard.py` → check the printed counts → import the
   printed `tmp/<name>-dashboard.json` into Grafana. (`uv run pytest -q` with no
   arg builds them all.)

## Round-tripping from the Grafana UI

The build is one-directional (files → JSON). When a dashboard is edited live in
Grafana, bring the change back into source:

1. Pull the live dashboard (Grafana UI export, or the Grafana MCP
   `get_dashboard_by_uid` / `get_dashboard_property` tools).
2. Split each panel back into its `NN-<slug>.json` file and update
   `dashboard.meta.json` for any variable/time/tag changes.
3. Bump `version` in `dashboard.meta.json`.
4. `python scripts/build-dashboard.py` and diff `tmp/<name>-dashboard.json` against
   the live export to confirm parity.

> Never let the UI become the source of truth — the per-panel files are authoritative.

The `/merge-grafana-dashboard <name>` command automates this reconciliation: it fetches
the live dashboard via the Grafana MCP, diffs it against the on-disk build, merges drift
back into the per-panel files, and rebuilds. (Requires the `grafana` MCP.)

## `dashboard.meta.json` skeleton

Everything that is not a panel. Minimal shape:

```jsonc
{
  "title": "My Service",
  "uid": "myservice1",            // unique; matches the dashboard in Grafana
  "tags": ["my-team", "service"],
  "editable": true,
  "schemaVersion": 40,
  "graphTooltip": 1,               // 1 = shared crosshair
  "time": { "from": "now-1h", "to": "now" },
  "timezone": "browser",
  "annotations": { "list": [ /* built-in "Annotations & Alerts" */ ] },
  "templating": { "list": [ /* variables — see panel-anatomy.md */ ] },
  "links": [],
  "version": 1
}
```

The build merges `panels` into this object; do not put a `panels` key in the meta file.
