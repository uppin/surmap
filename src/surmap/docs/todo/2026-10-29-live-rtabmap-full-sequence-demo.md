# 2026-10-29 — Full-sequence demo verification of the live RTAB-Map map

**Category:** Blocked externally
**Source:** `docs/surmap/1-WIP/2026-10-29-live-rtabmap-streaming.md` (M6)
**Packages:** surmap
**Consent:** n/a — blocked externally (see below)
**Status:** Open

## What is left

Run the full-sequence manual verification (PRD milestone M6):

```bash
uv run python scripts/demo.py --coral-model-dir tests/fixtures/coral_model
```

over the full EuRoC V1_01 sequence (2,912 pairs) and record in the
changeset's `## Verification`: that the map grew during playback (not
only at the end), the final keyframe count, SLAM lag in frames,
dropped frames, the measured frame-to-map latency p50/p95 at demo
pacing, and a screenshot path of the live map panel.

## Why it could not be done now

The full dataset (~1.1 GB zip) is not in the local demo cache
(`~/.cache/surmap/demo-datasets/euroc-v1-01-easy/`) on the machine
that implemented the streaming backend, and M6 is by definition a
manual, in-browser verification — a human opens the demo page and
watches the map panel grow. Neither the download nor the eyeball
check could be completed in the implementing session. Routes around
it were considered: substituting the 90-pair fixture replay (done —
that is the real-container e2e, not the full-sequence demo) and
claiming M6 from it (wrong: it would overstate what was verified).

## What was done instead

The 90-pair real-container e2e (`tests/test_slam_streaming_e2e.py`,
`SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1`) passes, and an unpaced probe
over the same fixture recorded odometry+SLAM median 37.0 ms /
p95 53.9 ms per frame, 0 lost frames with stereo-only VO, and
frame-to-keyframe latency p50 0.712 s / p95 0.823 s under queue
backlog. Numbers are in the changeset's `## Verification`.

## When it becomes possible

As soon as a developer runs the demo on a machine with the full
dataset cached (first `scripts/demo.py` run downloads it) and can
open the page in a browser. Delete this file in the commit that
records the M6 results.
