---
description: Reconcile a live Grafana dashboard with its on-disk per-panel source, merging UI drift back into the files, then rebuild
argument-hint: <dashboard-name>
---
Reconcile the **live** Grafana dashboard with the **on-disk** per-panel source under
`grafana/<dashboard-name>/`. People edit dashboards both in the Grafana UI and in these
files; this command captures UI-side drift back into the source-of-truth (the per-panel
files), then rebuilds the importable JSON.

Target dashboard: **$ARGUMENTS**

See the `build-grafana-dashboards` skill (`.agents/skills/build-grafana-dashboards/`) for
the layout, build contract, and panel/variable anatomy used when splitting JSON back into
files.

## 0. Preconditions — STOP if not met

1. **Dashboard name.** If `$ARGUMENTS` is empty, list the directories under `grafana/`
   (those containing `dashboard.meta.json`) and ask which one. Do not guess.
2. **Source exists.** Read `grafana/$ARGUMENTS/dashboard.meta.json`. If it's missing,
   STOP and report the available dashboards.
3. **Grafana MCP is required.** Extract `uid` from the meta file and call the Grafana MCP
   `get_dashboard_summary` (uid). **If the Grafana MCP tools are unavailable or the call
   fails because the server isn't connected, STOP immediately** — print that the `grafana`
   MCP must be enabled to run this command, and do not continue. This command cannot work
   from local files alone.

## 1. Fetch the live dashboard

- Call `get_dashboard_by_uid` (uid). Use the `.dashboard` object (ignore the `.meta`
  wrapper). Large dashboards may be written to a results file — read it fully if so.

## 2. Build the on-disk version

- Run `python scripts/build-dashboard.py` → produces `tmp/$ARGUMENTS-dashboard.json`.
  This is the assembled representation of the current source files. Treat it as the
  "disk" side.

## 3. Diff live vs disk

Compare the two dashboard objects structurally, not as raw text:

- **Panels** keyed by `id` (fall back to `title` + `gridPos` if ids drift): added,
  removed, or modified. For modified panels, diff `targets` (queries), `gridPos`,
  `fieldConfig`, `options`, `title`, `type`.
- **Templating** variables, **time**, **tags**, **annotations**, and other meta.
- **Normalize / ignore volatile fields** that always differ and must NOT drive a merge:
  - `version`, top-level `id`, `iteration`
  - template variable runtime state: `current`, populated `options`
  - echoed defaults that Grafana re-serializes (e.g. base threshold `value` null↔0)

  Report these as "ignored" rather than as changes.

Summarize the diff as: live-only changes, disk-only changes, and genuine conflicts
(both sides changed the same panel/field differently).

## 4. Merge strategy (agent applies)

Goal: the per-panel source files end up representing the intended union of both sides.
There is no common ancestor, so reconcile per panel/field:

- **Changed on one side only** → take that side automatically.
- **Conflict (both sides changed)** → DO NOT silently pick. Surface both values with a
  short recommendation and ask the user (use the question tool) which to keep. Prefer the
  live value for layout/visual tweaks; prefer the disk value for query/logic changes
  unless the user says otherwise.
- **Panel added in live** → create a new `NN-<slug>.json` in the matching section
  (choose the section by the panel's `gridPos.y` / neighbouring panels; ask if unclear).
- **Panel removed in live** → ASK before deleting the corresponding source file.
- Keep `uid` from the on-disk meta. Set `version` in `dashboard.meta.json` to the live
  `version` (so the next import is clean).
- Strip runtime-only fields (`current`, populated `options`, top-level `id`) when writing
  variables/meta back to source, unless a value is intentionally pinned.

## 5. Apply to the source files

**CRITICAL:** the build regenerates `tmp/` *from* the source files, so the merge must be
written into the source files — never into `tmp/$ARGUMENTS-dashboard.json` (that is
generated output and will be overwritten).

- Split merged panels back into their `grafana/$ARGUMENTS/NN-<section>/NN-<slug>.json`
  files (one panel per file), preserving section/order conventions.
- Update `grafana/$ARGUMENTS/dashboard.meta.json` for templating/time/tags/version changes.

## 6. Rebuild and verify

- Run `python scripts/build-dashboard.py` again.
- Re-diff the rebuilt `tmp/$ARGUMENTS-dashboard.json` against the live JSON from step 1.
  The only remaining differences should be the normalized/ignored fields (version, runtime
  state). If anything else differs, the merge is incomplete — fix the source files and
  rebuild.

## 7. Report

- Summarize what was taken from live, what from disk, conflicts and how they were resolved,
  and any files created/deleted.
- Note that pushing back to Grafana is manual: the `grafana` MCP is read-only for
  dashboards, so import `tmp/$ARGUMENTS-dashboard.json` via the Grafana UI if you want the
  merged result live.

## Guardrails

- **STOP** before step 1 if the Grafana MCP is unavailable.
- **ASK** before deleting any source panel file.
- **Never** hand-edit `tmp/*-dashboard.json`.
- **Don't** silently resolve genuine conflicts — surface them.
