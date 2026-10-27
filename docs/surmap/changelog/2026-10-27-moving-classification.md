# Area verdicts, tracked keypoints and observation buffer

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Implemented design steps 3–5 of the moving-object pipeline: the
per-track motion-statistics accumulator (`TrackMotionStats`:
net/path ratio, velocity coherence, Welford area variance) and
terminal, versioned verdict machine (`surmap.moving.classify`,
RIGID_MOVER / OSCILLATING / UNKNOWN from ≥5 observations over
≥1 s); FPS + PCA-endpoint keypoint selection from the dynamic
candidates with bounded Lucas–Kanade identity tracking and one
ego-compensated constant-velocity filter
(`surmap.moving.keypoints`); and the 3 s observation ring
buffer (`surmap.moving.buffer`) that retrospective placement
consumes.

Verification: red-first unit tests (7 failed at the red commit)
green at implementation; on the wrapped tip `uv run pytest -q`
465 passed, `uv run mypy` strict clean, `uv run ruff
check`/`format` clean.

Deferred, each with its record under `src/surmap/docs/todo/`:
detector-track identity adoption in the stream handler
(snapshots carry area-allocated identities until then), and
snippet acceptance runs with split-half threshold tuning
(blocked on the dataset spikes). Both gate on-board enablement,
not this node's merge.
