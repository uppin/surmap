# Demo run export and import (`.surmaprun`)

**Date:** 2026-11-02
**Feature:** Dev console run history

A recorded run can leave one console and join another. **Export** downloads the selected
run as a `.surmaprun` file (`GET /runs/<id>/export`), and **Import** uploads one
(`POST /runs/import`). The CLI does the same headlessly:
`python -m surmap.demo.run_archive export RUN_ID FILE` and `import FILE`
(`--history-db`).

**The format.** A file is a gzipped SQLite database in the run history's own schema
(`history.SCHEMA`):
- it holds the run and every run its replay lineage reaches, since a replay answers its
  regions from its source's rig and dense buffer;
- plus `export_info(format_version, run_id, exported_at)`.

So an imported run replays and rewinds like one recorded there.

**Import behaviour.**
- Runs keep their ids: a run already present is skipped, and a second import changes
  nothing.
- AUTOINCREMENT rows (map updates, detections, surfaces, journal events) are renumbered
  in their order.
- A file without `export_info`, or not gzip or SQLite at all, is refused
  (`NotARunArchive`, HTTP 400).
- A run still recording cannot be exported (`RunNotExportable`, HTTP 409).
- Both directions go through the console's own store connection under its lock
  (`RunHistoryStore.exclusive`), so nothing writes mid-copy.

Verification:
- Gates green; `tests/test_demo_run_archive.py` covers the round trip, a replay's
  lineage, re-import, refusals, HTTP and the CLI.
- The KITTI 0009 SAM run `acdcc6aa` (447 frames, about 600 MB of rows) exported in 30 s
  to 198.8 MB. Imported into a fresh history, all nine tables matched the original row
  for row (per-table counts and checksums), and the snapshot at frame 200 was identical.
