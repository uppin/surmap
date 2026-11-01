# Map-frame moving-object snapshots at RTAB flush

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Implemented design steps 6–7 of the moving-object pipeline:
retrospective placement (`surmap.moving.placement` —
VO-increment correction distribution between bracketing
keyframe poses, snapshot construction, the disjoint
detector/area-allocated designation space; a designation is a map-layer id) and the assembled
`StreamMovingAreas` handler (in `surmap.survey.moving_stream`,
split out of `cm5_server` at wrap: 526 → 296 lines, verified
behaviour-preserving by line-set fidelity diff), which runs
stages 1–5 live and publishes map-frame `MovingObjectSnapshot`
messages at RTAB flush.

Verification: red-first unit tests green; handler-level stream
test green; and the KITTI stereo E2E
(`tests/test_moving_kitti_e2e.py`, `SURMAP_REQUIRE_KITTI_E2E=1`)
through the real `SidecarRtabmapBackend`: 8 keyframe poses,
27.7 m trajectory, car-proximate clusters on all 8 keyframes,
graduated track, nearest snapshot 1.32 m from a labelled car.
On the wrapped tip `uv run pytest -q` 470 passed, `uv run mypy`
strict clean, `uv run ruff check`/`format` clean.

Recorded findings: RTAB's exported cloud is near-empty at
driving depths (56 points), so layer seeding falls back to
segment hit-counts; subpixel disparity (PR #25) is a stage-1
prerequisite at driving range. Deferred in
`src/surmap/docs/todo/2026-10-27-moving-runtime-vo-increments.md`:
runtime VO increments for correction distribution (placement
currently degrades to time-fraction interpolation). Gates
tighter placement claims, not this node's merge.
