# Dataset runs cache — initial discovery

**Date:** 2026-11-04

- The demo console already reruns a scene's cached recording:
  `RunHistoryStore.latest_recording` (newest complete, journalled, non-replay run), played from
  its journal with `record=0`; only Rebuild records (`2026-11-02-cached-reruns`).
- The agent's `run_demo` / `run_rtabmap` (`DemoWorkspace._run_recorded`) always recorded a new
  run, so every gallery Run button re-ran RTAB-Map, dense depth and SAM.
- A run's title encodes the SAM prompt and on-board model, but not its frame limit, so a title
  cannot key a cache on its own.
- The gallery reads `GET /datasets` (`routes._dataset_json`), not the proto; the frame route
  `/frames/<run>/<frame>.jpg?max_side=` can serve a run preview.
- Run archives copy `RUN_TABLES`; an older archive lacks any new table, so a new table there
  would break their import.
