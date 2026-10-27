# Demo launcher

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added `scripts/demo.py`: downloads and caches a recorded dataset on
first run, then serves a browser demo — real-time video with the
stereo reconstructor's scene points overlaid as depth-coloured
detections, and at the end of playback the real RTAB-Map map (poses,
travelled distance, assembled cloud drawn top-down) built by the
sidecar from the same frames.

Datasets are an extensible registry (`surmap.demo.datasets.DATASETS`,
one `DatasetSpec` per entry): the zip is fetched once into
`~/.cache/surmap/demo-datasets` (or `--cache-dir`), verified by size
+ pinned SHA-256, extracted, and indexed in a manifest; later runs
are pure cache hits. First entry: full EuRoC V1_01_easy (2,912 pairs,
zip SHA-256 `a920fe5b…`). Playback is paced server-side at `--fps`
(first frame promptly, no catch-up bursts); the demo server is
stdlib `http.server`, one viewer at a time, and the sidecar is
closed on completion, disconnect, or error. A shared container named
by `SURMAP_RTABMAP_SHARED_CONTAINER` is borrowed, never removed.

Verification: registry/cache/projection/server tests (tiny synthetic
zip, real HTTP smoke with the server closed afterwards), plus a real
run against the cached EuRoC dataset — 30 pairs from index 400
streamed 30 frame events with 600 overlay detections each and a
final RTAB-Map result (2 poses, 0.392 m, 5,750 cloud points).
