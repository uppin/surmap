# Moving-object snippet fixtures and candidate seam

**Date:** 2026-10-27
**Type:** Infra
**Packages:** surmap

Added the evaluation-fixture layer of the moving-object stack:
`surmap.moving.snippets` (snippet registry, VisDrone-MOT and
Purdue oracle converters, KITTI calibration → EuRoC `sensor.yaml`
derivation), the `CandidateCluster` seam type in
`surmap.moving.candidates` that stages 1–2 meet at, and
`scripts/fetch_moving_snippets.py`, which range-extracts one
KITTI sequence from the two ~15 GB tracking zips (zip64 central
directory, one contiguous span per sequence, `training/` members
only, both stereo channels, frame-range filter, SHA-256 cache
manifest). KITTI sequence 0020 was fetched and verified live
(baseline 0.5323 m from its calib file).

Verification: red-first fixture tests (4 failed / 2 passed at the
red commit) green at implementation; on the wrapped tip
`uv run pytest -q` 446 passed, `uv run mypy` strict clean,
`uv run ruff check`/`format` clean.

Deferred, recorded in
`src/surmap/docs/todo/2026-10-27-moving-snippet-dataset-spikes.md`:
the three monocular dataset spikes (Boreal/Wennington, VisDrone
sequence pick, Purdue window pick, COLMAP fx cross-check) —
deferred by the developer's direction to put the effort on the
KITTI stereo E2E; they gate snippet acceptance tests and
on-board enablement, not this seam.
