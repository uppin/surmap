# Static-layer differencing and moving areas stream

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Implemented design steps 1–2 of the moving-object pipeline: the
log-odds static layer with dwell-gated absorption, candidate
penalty and lazy decay (`surmap.moving.differencing`), the
τ(Z, θ̂) noise-scaled static test (own/neighbour fast path plus
coarse-gated chunked-numpy exact stage, ~0.018 s per 4k-point
frame on the dense workload), grid-hash candidate clustering
with cluster-level persistence (never per-voxel recurrence, so
fast vehicles survive), moving-area polygons with centroid
area tracks (`surmap.moving.areas`), and the `StreamMovingAreas`
ConnectRPC stream publishing live `MovingArea` messages keyed by
frame_id.

Verification: red-first unit tests (7 failed at the red commit)
green at implementation; on the wrapped tip `uv run pytest -q`
456 passed, `uv run mypy` strict clean, `uv run ruff
check`/`format` clean.

Deferred, recorded in
`src/surmap/docs/todo/2026-10-27-moving-euroc-negative-control.md`:
the EuRoC negative-control replay (zero false graduations on a
static scene) — it needs the handler assembly that landed at
n5; the positive control (KITTI) landed green in PR #23. Gates
on-board enablement, not this node's merge.
