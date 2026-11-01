# SAM region → dense 3D points (`StreamRegionPoints`)

**Date:** 2026-10-31
**Feature:** Survey data APIs / RTAB-Map streaming sidecar / browser demo

A SAM mask can now be placed in 3D with full detail. The new BIDI rpc
`Cm5SurveyService.StreamRegionPoints` takes a frame id, the channel
the polygon was drawn on (0 left / 1 right) with that image's size,
and the polygon; it answers with every point dense stereo recovers
inside the polygon on that one frame, in the map frame, chunked with
`final` on the last message. Nothing accumulates across frames or
queries, so the shape is instant and is exactly what SAM outlined.
`FRAME_EXPIRED`, `NO_POSE` and `INVALID_QUERY` are explicit statuses.

RTAB-Map's own 2D→3D link is its sparse visual words (left image
only, ~1000 per frame); its keyframe cloud is 5 cm-voxelled and
keyframe-only. The streaming sidecar (protocol v4) therefore keeps a
time-bounded ring of uncompressed rectified pairs and odometry poses
(`region_buffer_s`, default 10 s) and answers `region` requests with
OpenCV SGBM over the polygon's rows, the requested channel as the
reference image (the right one matched in mirrored images), placed
with the current map correction × the frame's odometry pose. The
backend sends region requests ahead of queued pairs, never drops them,
and matches answers to callers by `query_id` (`slam/stream_outbox.py`).

The CM5 gained `--slam-backend streaming` (`--frame-size`,
`--region-buffer-s`), which serves both live poses and regions. The
demo places each SAM result's masks in 3D (`region` SSE events,
≤ 50 000 points each) and the 3D pane draws the latest region over
the cloud; `--sam-fake` runs a stand-in SAM (centre of every frame)
so this works without a GPU.

To keep the oversized demo files from growing, `DemoEvent` and the SAM
event builder moved to `demo/events.py` (re-exported from
`demo/server.py`), the streaming process seam to
`slam/stream_process.py`; `demo/server.py` (1514 lines) and
`demo/page.py` (525) are recorded under `src/surmap/docs/code-issues/`.

Verification: gates green (ruff, format, mypy strict, pytest with the
real-container e2e required). On the EuRoC V1_01 fixture (376×240,
amd64 emulated on Apple Silicon) a 140×100 px box returns ~15 300
points on either channel against 40 sparse inliers, in 36–65 ms; the
whole view ~67 000–70 000 points in 140–160 ms; channel-1 points lie
a median 0.7 cm (p90 1.8 cm) from the channel-0 surface. A 200-frame
demo run with the fake SAM produced 200 region events, 199 placed with
~8 300–8 800 points each (the last SAM result arrives after the
sidecar's input closed).
