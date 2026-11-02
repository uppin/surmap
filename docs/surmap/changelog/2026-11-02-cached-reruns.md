# The console reruns cached recordings; only Rebuild records

**Date:** 2026-11-02
**Feature:** Browser demo / run history / journal replay

Opening the test console used to start a live run every time: RTAB-Map
in Docker and, if enabled, SAM. Every page load, reload or second tab
recorded another run, and with two tabs each reconnect took the run back
from the other. Now:

- **Default: cached rerun.** The page reruns the scene's cached run,
  `RunHistoryStore.latest_recording`: its newest *complete*, journalled
  recording, never a replay. It plays from the journal at 1×
  (`/stream?replay=<id>&speed=1&record=0`), and `record=0` persists
  nothing. The run event names the recording itself, so the timeline
  scrubs it. `/datasets` lists each scene's `cached_run`. A scene
  without one plays nothing and asks for a Rebuild.
- **Rebuild** replaces Restart. It is the only action that runs RTAB-Map
  (and SAM) and records a new run. Applying a new SAM prompt is a
  rebuild (`rebuild=1`), since it needs fresh SAM results. Explicit
  **Replay run** still records the replay as a run naming its source,
  for comparing tuned logic.
- **Cut-short runs are interrupted.** A live run cancelled by a takeover
  used to be stored as `completed` (the player returns normally when
  cancelled). It is now `interrupted`, so a fragment never becomes the
  cached run.
- **One PNG decode per frame.** `DenseBufferRegionSource` decodes each
  frame's disparity once for all of its masks, instead of once per mask:
  −36 % replay CPU on KITTI.

Verification: gates green; both rendered page scripts pass
`node --check`. In the in-app browser, a console without SAM opened on
KITTI 0009 reruns the 447-frame SAM recording with its SAM pane drawing,
and the history keeps the same 30 runs. Rebuild is present and Restart
is gone.
