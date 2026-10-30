# Live RTAB-Map streaming backend

**Date:** 2026-10-29
**Feature:** RTAB-Map SLAM backend / browser demo

The RTAB-Map map is now built in real time. A long-lived
`surmap-rtabmap-stream` sidecar — librtabmap embedded in a small C++
tool built into a derived image FROM the pinned RTAB-Map image —
consumes stereo pairs over stdin/stdout and emits the visual-odometry
pose per pair, keyframe points per new keyframe, and optimized graph
poses on re-optimization and at end of stream. Stereo only: no IMU,
no wheel odometry.

`surmap.slam.StreamingRtabmapBackend` never blocks playback: pairs go
through a bounded drop-oldest queue (drops counted), a reader thread
applies odom/keyframe/graph updates, and `map_snapshot()` re-places
keyframe points whenever the optimized graph moves them. Its
`flush()` returns the batch-compatible shape, so existing callers
keep working. The batch sidecar and the CM5 server are unchanged;
shared-container mode is rejected explicitly for streaming.

The demo (default `--rtabmap-mode live`) emits throttled `map` SSE
events during playback; the map panel grows frame by frame and shows
keyframe count, cloud size, odometry state, lag and dropped frames.
`--rtabmap-mode batch` preserves the previous behaviour.

Verification: gates green (ruff format/check, mypy strict, pytest);
real-container e2e over the 90-pair fixture passes with live updates
before flush; full-sequence demo numbers are recorded in PR #38.
Measured on the implementing host (native amd64): odometry+SLAM
median 37 ms / p95 54 ms per frame on the 90-pair fixture, zero lost
frames; full-sequence (2,912-pair) frame-to-map latency p50/p95 and
final keyframe/lag/dropped counts are in the PR verification record.
