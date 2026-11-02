# Initial Discovery — demo dense depth misses KITTI / EuRoC frames

## Combined Conclusions

- The page's "Dense depth" toggle answers "Dense depth unavailable for this frame." on KITTI
  0009 and EuRoC V1_01, and works on NTU VIRAL.
- `GET /dense-depth` matches `t_ns` exactly against `PreparedDataset.timestamps_ns`
  (`src/surmap/demo/server.py` `_dense_depth`); an unknown `t_ns` is a 404, and the page shows
  the "unavailable" line on any failed load (`src/surmap/demo/page.py` `loadDense`).
- The page gets `t_ns` from JSON numbers: the SSE `frame` event (`data.t_ns`, built in
  `server.py` `_FrameGate.release`, or replayed verbatim from the journal by
  `replay.JournalPlayer`) and the scrub snapshot (`snap.t_ns`, `history.snapshot_at`).
- Epoch-nanosecond stamps (~1.3e18) exceed 2^53. The browser keeps the nearest double and
  prints the shortest decimal for it, so `String(1317042515215464704)` is
  `"1317042515215464700"` → 404.
- Measured on the cached scenes (`String(Number(t)) !== t`): KITTI 429/447, EuRoC 2912/2912,
  NTU VIRAL 0/3540.
- The page uses `t_ns` only for the dense-depth request (lines 365, 476 → `drawImageFrame` →
  `loadDense`). Other consumers of event `t_ns` are server-side Python (`int(str(...))`).

## Exploration 1

Parent-driven grep / read, 2026-11-02.

- `src/surmap/demo/page.py:260-282` — `loadDense(tNs)`; URL is
  `'/dense-depth?dataset=' + … + '&t_ns=' + encodeURIComponent(tNs)`.
- `src/surmap/demo/page.py:365, 476` — `drawImageFrame(..., snap.t_ns)` and `(..., data.t_ns)`.
- `src/surmap/demo/server.py:2080-2091` — `_dense_depth`: `int(query["t_ns"])`, 404 when not in
  `prepared.timestamps_ns`.
- `src/surmap/demo/server.py:2140-2144` — SSE writer: `payload = dict(event.data)` →
  `json.dumps`; the single place every published event (live and replay) is serialised.
- `src/surmap/demo/history.py:545-556` — `snapshot_at` returns `"t_ns": int(frame["t_ns"])`.
- `tests/test_demo.py` `_tiny_zip` / `_prepared_tiny` — the tiny scene, stamps fixed at 100, 200.
- `tests/test_demo_dense_depth.py` — server and page tests for dense depth; all use t_ns 100.
- Reproduced against a running console (KITTI, port 8766): exact stamp → 200, the page's
  rounded text → 404.

## Exploration 2

Re-plan after the user's direction "RTAB-Map is the source of truth also on frame level".

- NumPy matcher vs journalled SGBM on 6 KITTI frames of run `acdcc6aa`
  (scratch script, display 620×188, fB 193.5 px·m): SGBM covers 51–69 % of pixels; NumPy
  @160 px 12–34 %, median error 39–85 %; NumPy @620 px 7–12 %, median error 51–67 %.
- `src/surmap/slam/dense.py` — `DenseFrame` (frame_id, t_ns, channel, to_map, 16-bit PNG
  at 1/16 px), `dense_region_points` geometry (display → raw → `undistort_points` → `lround`),
  `project_to_display`.
- `src/surmap/demo/history.py` — `record_dense` (live, per `dense` event), `dense_frames`,
  `rig`, `root_run` (a replay's recording).
- `src/surmap/demo/replay.py` `_placer` — replays read `dense_frames(root_run(...))`.
- `deploy/rtabmap-stream/main.cpp` `fullFrameDisparity` — SGBM once per frame on its first
  region query, so only SAM frames have a dense buffer.
- `src/surmap/demo/sam_depth.py` — SAM pane colours each object over its own range, not the
  absolute stops.
- `src/surmap/mission/dense.py` `DenseStereoFallback` — also NumPy; mission path, untouched.
