# Initial Discovery: Demo run export and import

**Changeset**: [2026-11-02-demo-run-export-import.md](./2026-11-02-demo-run-export-import.md)
**Date**: 2026-11-02
**Passes**: 1

## Combined Conclusions

- **Where runs live.** A demo run lives in `RunHistoryStore` (`src/surmap/demo/history.py`):
  one SQLite file (`<cache>/demo-history.db`, 3.5 GB on this machine), nine tables keyed
  by `run_id`:
  - `runs`, `frames` (JPEG blobs), `maps`, `detections`, `surface_points`, `events` (the
    journal);
  - `run_rigs`, `dense_frames` (disparity PNG blobs), `run_sources`.
- **Row ids.** `maps`, `detections`, `surface_points` and `events` have AUTOINCREMENT ids
  whose order is the playback order, so an import must renumber them and keep that order.
- **Replays depend on their source.** A replay's regions come from its root run's rig and
  dense buffer (`root_run`, `JournalPlayer._placer`), so exporting a replay must include
  its source chain.
- **Size.** `acdcc6aa` (KITTI 0009, 447 frames, SAM 3.1) is about 600 MB of row data:
  events 316 MB, maps 216 MB, surface points 25 MB, dense frames 21 MB, frames 17 MB.
  It is mostly JSON text, so gzip pays off.
- **Server side.** The HTTP handler serves `/runs`, `/runs/<id>`, `/runs/<id>/snapshot`;
  POSTs go to `/control`. The page lists runs (`refreshRuns`) and has Load run / Replay run
  buttons.

## Exploration 1: run storage — 2026-11-02

**Agent**: parent Grep/Read
**Scope**: what a run is made of and how it is served

### Sequence

1. Grep `CREATE TABLE|CREATE INDEX` in `src/surmap/demo/history.py` — the schema.
2. Read `history.py` `root_run`, `source_run` — the replay lineage.
3. sqlite3 byte counts per table for `acdcc6aa952940be` — the size to expect.

### Findings

As above. No existing export or import code (grep `export|import_run` in `src/surmap/demo`).
