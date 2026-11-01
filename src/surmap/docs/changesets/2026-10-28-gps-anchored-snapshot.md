# GPS-anchored semantic map snapshot

**Date:** 2026-10-28
**Type:** Feature
**Packages:** surmap

Added `surmap.map.snapshot`: `build_snapshot` classifies
`ObjectTrack3D` tracks with `classify_motion`, writes static and
unknown tracks to `landmarks` and moving tracks to `dynamic`, and
anchors each track to the nearest `GpsCheckpoint` by `t_ns`
(`offset_ns`). The earliest fix is the ENU origin; with no fix the
origin and the geodetic fields are absent. Landmark `id` is the
decimal track id. `mask_points` is an optional map-frame xyz list.
`write_snapshot` writes UTF-8 JSON and `read_snapshot` returns the
same snapshot. Schema: `docs/semantic-map-snapshot.md`.

Verification: V1 fail→pass, 19 snapshot tests red on
`NotImplementedError` then green. On the wrapped tip `uv run pytest -q`
reported 487 passed and 5 skipped; mypy strict and Ruff were clean.
