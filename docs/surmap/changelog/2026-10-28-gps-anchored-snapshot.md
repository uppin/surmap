# GPS-anchored semantic map snapshot

**Date:** 2026-10-28
**Feature:** Semantic map snapshot

Added a UTF-8 JSON export of the semantic map
(`surmap.semantic_map_snapshot.v1`, `docs/semantic-map-snapshot.md`).
`build_snapshot` calls `classify_motion`, keeps moving tracks in
`dynamic`, and anchors every other track as a landmark. The origin is
the earliest GPS fix, or absent when there is no fix. `offset_ns` is
the signed gap to the nearest fix by time. Each landmark has a stable
decimal track `id` and an optional map-frame `mask_points` list.
`write_snapshot` / `read_snapshot` round-trip the file. GeoJSON remains
an open decision.

Verification: V1 fail→pass. Before the implementation,
`tests/test_map_snapshot.py` had 19 failures (`NotImplementedError`).
On the wrapped tip, `uv run pytest -q` reported 487 passed and 5
skipped, and `uv run mypy`, `uv run ruff check src tests`, and
`uv run ruff format --check src tests` were clean.
