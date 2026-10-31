# Initial discovery — generic test console

Date: 2026-10-31

## Current state

- Page: [src/surmap/demo/page.py](/home/mantas/Code/surmap/src/surmap/demo/page.py) — titled
  "SurMap demo", video canvas `#view`, 2D floor-plan canvas `#map` (340×340,
  server-rendered PNG from `render_floor_plan` in
  [src/surmap/demo/server.py](/home/mantas/Code/surmap/src/surmap/demo/server.py)).
  No history, no persistence, no 3D view, map pane fixed size.
- Server: `DemoPlayer.events()` yields `frame` / `map` / `detections` /
  `status` / `final` SSE events. Map/final events carry `floor_png`,
  `extent`, `trajectory_xy`, stats — no raw cloud points, so a browser
  3D view and per-moment cloud replay are impossible today.
- No SQLite use anywhere in `src/surmap/demo/`; runs vanish on disconnect.
- Controls today: scene picker, Pause/Resume (`POST /control`), Restart
  (page reload). A new viewer takes the stream over.

## What the request needs

1. Generic testing page (not a per-dataset demo narrative): test-console
   framing, any registered scene, run controls, run status.
2. Persist every run to SQLite; rewind / wind forward through the run
   with the frame image, overlay points, detections and the point cloud
   as they were at that moment (latest map snapshot at or before the
   scrubbed frame), not the final cloud.
3. Point-cloud pane: resizable, fullscreenable, PTZ (pan / tilt / zoom)
   controls — a real 3D point view, so map events must carry sampled
   raw cloud points + colours alongside the floor-plan PNG (kept for
   compatibility and as the 2D mini-map).

## Decisions

- Stdlib `sqlite3` only (no new dependency). New module
  `src/surmap/demo/history.py` (`RunHistoryStore`), DB default
  `<cache-dir>/demo-history.db`, overridable (`--history-db`).
- Persistence at the HTTP stream layer: `_stream` records each event
  as it is sent; a first SSE `run` event carries the new `run_id`.
- History API: `GET /runs`, `GET /runs/<id>`, `GET /runs/<id>/snapshot?seq=N`.
- Browser cloud: raw WebGL points (no external JS deps, page stays
  offline/self-contained), orbit PTZ state (azimuth/elevation/distance/
  target), button + mouse + wheel controls.
- Display cloud capped server-side (even sample) so SSE and DB stay
  bounded; the full cloud count is still reported as `cloud_points`.
