# Changeset: Live RTAB-Map streaming backend

**Date**: 2026-10-29
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — several row-4 signals: new C++ tool + wire protocol + threaded backend + demo wiring + CI job

## Workflow

- [wf 1] ✅ 2026-10-29 `/plan-red` Plan — PRD, changeset, initial discovery · PRD in this file's PRD section; discovery companion written
- [wf 2] ✅ 2026-10-29 `/plan-red` Red — acceptance and failing lower-tier tests, committed · protocol/streaming/demo tests red on missing modules, then green
- [wf 3] ✅ 2026-10-29 `/green` Green — implement until every red test passes · 483 passed, 1 skipped; streaming e2e green
  - [x] M0 spike: minimal tool in derived image; record ms/frame, keyframes, tracking on 90-pair fixture
  - [x] M1 protocol codec (pure encode/decode, typed dataclasses)
  - [x] M2 C++ tool `surmap-rtabmap-stream` (hello/ready, odom, keyframe, graph, final, lost)
  - [x] M3 `StreamingRtabmapBackend` (non-blocking, drop-oldest, poll_updates, map_snapshot, flush shape)
  - [x] M4 demo live map (`map` SSE ~2–4 Hz, `--rtabmap-mode {live,batch}`)
  - [x] M5 real-container e2e + CI job + `scripts/build_rtabmap_stream.py`
  - [ ] M6 manual full-sequence verification recorded — deferred: `src/surmap/docs/todo/2026-10-29-live-rtabmap-full-sequence-demo.md` (full dataset not cached locally; 90-pair e2e + probe recorded below instead)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `README.md` — Demo + RTAB-Map note updated to State B
  - [ ] `docs/architecture.md` §4.1 / §9 — streaming backend described
  - [ ] `docs/surmap/changelog/` entry written
  - [ ] PRD, this changeset and discovery companion deleted from `1-WIP/`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-29-live-rtabmap-streaming-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## PRD

Requirement input: *Live RTAB-Map streaming backend* (2026-10-29, Technical Improvement, Feature · adds). Headline: map built in real time — each keyframe's points on the demo map within ≤ 1 s of its frame playing (target; record p50/p95). Stereo only: no wheel odometry, no IMU. Long-lived sidecar embedding librtabmap over stdin/stdout; `StreamingRtabmapBackend`; demo `map` events; real-container e2e + CI job. CM5 keeps the batch sidecar. Full PRD text was supplied with the task and is the requirement source for the rows above.

## Summary

Add a streaming RTAB-Map backend beside the batch sidecar: a C++ tool in a derived image consumes stereo pairs over a pipe and emits odometry, keyframe points and optimized graph poses live; the demo map grows during playback.

## Background

`SidecarRtabmapBackend` is batch by construction; the demo map appears only after playback ends. RTAB-Map ships no live CLI, so embed `librtabmap` in a small C++ program in the pinned image, driven over stdin/stdout. ROS 2 rejected as too large a dependency.

## Scope

- C++ tool `surmap-rtabmap-stream` + derived image `surmap/rtabmap-stream:<sha12>` FROM the pinned digest.
- Versioned binary-safe wire protocol + pure Python codec.
- `StreamingRtabmapBackend` (threads, drop-oldest backpressure, `poll_updates`, `map_snapshot`, batch-compatible `flush()`).
- Demo live map + `--rtabmap-mode {live,batch}`; batch path and CM5 unchanged.

## Technical Changes

### State A (Current)

- Batch sidecar only; demo map at end; no runtime VO.

### State B (Target)

- Streaming backend satisfies `SlamBackend`; map snapshot re-places points on graph updates; lost tracking yields `pose=None`; demo emits throttled `map` events before `final`.

### Delta

- `deploy/rtabmap-stream/`, `src/surmap/slam/stream_protocol.py`, `src/surmap/slam/streaming.py`, `scripts/build_rtabmap_stream.py`, demo wiring, `tests/test_slam_streaming_e2e.py`, CI job.

## Verification

**Method:** V1-fail→pass — acceptance/unit tests red first, then green; plus V4 manual full-sequence run (M6).
**Command:** `uv run pytest -q` and the four gates in `AGENTS.md`.
**Before:** new streaming tests fail (modules missing).
**After:** all gates green; M0/M6 numbers below.

### M0 / M6 numbers

Measured 2026-10-29 on this host (native amd64 Linux, not emulated) over the 90-pair fixture, unpaced probe (`/tmp/measure_stream.py`):

- Odometry+SLAM cost: median 37.0 ms/frame, p95 53.9 ms/frame (56 odom messages; the rest dropped by the bounded queue under the unpaced probe).
- Tracking: held, 0 lost frames, stereo-only VO (no IMU/wheel input). Keyframes emitted: 55 messages; optimized trajectory: 14 poses.
- Frame-to-keyframe latency (unpaced, queue-backed): p50 0.712 s, p95 0.823 s — within the ≤ 1 s target even with backlog; at demo pacing (20 fps = 50 ms/frame vs 37 ms median cost) lag stays near one frame.
- Final cloud: 474,312 points (host-side snapshot; demo samples to 4,000). Dropped under unpaced load: 25. Wall time 6.8 s for 90 pairs.
- Real-container e2e (`SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1`): passed — live updates before flush, travelled > 0.3 m, > 5k final points, no owned container left.
- M6 full-sequence (2,912-pair) demo run: not executed — dataset not cached locally; deferred in `src/surmap/docs/todo/2026-10-29-live-rtabmap-full-sequence-demo.md`.
