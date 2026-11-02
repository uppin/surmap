# Segmentation replay journal — record RTAB-Map + SAM, replay without them

**Date:** 2026-11-02
**Feature:** Browser demo / demo run history / streaming sidecar

Tuning how SAM masks become object surfaces no longer needs RTAB-Map
or SAM on every try. Each demo run now journals what the segmentation
consumes into `demo-history.db`:

- `events`: every streamed event, in order. The rendered `cloud_png`
  is stripped, and region events keep only each region's
  `point_count`.
- `run_rigs`: the region rig and the display size.
- `dense_frames`: RTAB-Map's dense buffer, one disparity PNG and map
  transform per SAM frame and channel.
- `run_sources`: a replay's source run.

`/stream?replay=<run_id>&speed=1|4|0` (page: **Replay run**) plays it
back through `surmap.demo.replay.JournalPlayer`. Frames, map,
detections and SAM come from the journal. Regions are answered from
the journalled disparity (`surmap.slam.dense.DenseBufferRegionSource`)
and surfaces by a fresh `SurfaceAssigner`. The replay is recorded as a
new run with `replay_of`. `/runs` lists `replayable` and `replay_of`.

Sidecar (protocol v5): each ring frame's full-frame SGBM disparity is
computed once per channel, on its first region query, and reused. It
used to be one band SGBM per query, discarded after the answer. A
frame's map transform is frozen at that first query. `ready` carries
`region_rig` (size, baseline, depth cap, K/D/R/P per channel). With
`dense_journal` in the hello, the sidecar emits one `dense` line per
newly computed disparity (16-bit PNG, base64), before its region
answer. That disparity is the source of truth: Python repeats only the
polygon geometry. That is OpenCV's iterative `undistortPoints` in
numpy, a PIL raster, back-projection and the map transform. No OpenCV
is added. A v4 image or native binary is now rejected by version.

Verification: gates green (ruff, format, mypy strict, pytest 1049
passed / 12 skipped with the EuRoC fixture and the rebuilt image).
`tests/test_slam_streaming_dense_e2e.py` shows offline answers from the
journalled disparity matching the live sidecar on both channels. Live
on EuRoC V1_01 (120 frames, real sidecar, fake SAM): live run 34 s;
replay at max speed 10 s over HTTP, 2.0 s for the bare player. Both
streamed 120 frame / 120 sam / 120 region / 116 surface events, and
the replayed regions matched the live ones exactly on all 116 frames
(0.00 % point count, 0.00 mm centroid). Journal cost: 3.4 MB of
disparity per 116 frames. Runs recorded before this change hold no
journal and are listed as not replayable.
