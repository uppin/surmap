# SAM masks projected onto the cloud

**Date:** 2026-10-28
**Type:** Feature
**Packages:** surmap

Added `surmap.survey.mask_cloud.points_in_mask`. It projects
camera-frame points with the stereo rig, keeps those inside a SAM
polygon and inside `[0, width) × [0, height)`, and drops `z <= 0.05`.
When a pose is passed, each kept point goes through
`surmap.geometry.to_map_frame`; otherwise the camera-frame point is
returned. An empty polygon returns an empty tuple. The function takes
no SLAM backend and writes nothing back into RTAB-Map.

Verification: `uv run pytest -q tests/test_mask_cloud.py` (4 passed).
Full gates on the wrap: `ruff format --check`, `ruff check`, `mypy`
(strict), and `uv run pytest -q` (472 passed, 5 skipped).
