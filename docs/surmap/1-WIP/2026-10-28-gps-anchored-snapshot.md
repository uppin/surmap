# Changeset: GPS-anchored semantic map snapshot

**Date**: 2026-10-28
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — one package, a handful of new symbols, unit tests plus a stdlib JSON file round-trip, no external adapter

## Workflow

- [wf 1] ✅ 2026-10-28 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file; baseline 468 passed, 5 skipped
  - [x] Record initial discovery
  - [x] Cross-check src/surmap/docs/todo/ and src/surmap/docs/code-issues/
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7)
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Acceptance tests written and failing for the right reason
  - [ ] Unit/integration tests written and failing
  - [ ] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `build_snapshot` calls `classify_motion` and puts moving tracks only in `dynamic`
  - [ ] Each landmark anchors to the nearest `GpsCheckpoint` by `t_ns` and stores signed `offset_ns`
  - [ ] Origin is the earliest fix, or absent when there is no fix; lat/lon/alt are null without an origin
  - [ ] Landmark carries stable `id`, map xyz, lat/lon/alt, label, description, `model_id`, motion, and optional `mask_points`
  - [ ] `write_snapshot` writes UTF-8 JSON and `read_snapshot` round-trips it
  - [ ] Acceptance: two checkpoints, static landmark with non-zero `offset_ns`, moving track only under `dynamic`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/semantic-map-snapshot.md` — document the snapshot JSON schema, including stable `id` and optional `mask_points`
  - [ ] `docs/surmap/changelog/2026-10-28-gps-anchored-snapshot.md` — write the feature history entry
  - [ ] `src/surmap/docs/changesets/2026-10-28-gps-anchored-snapshot.md` — write the package history entry
  - [ ] Delete this changeset, the PRD, and the discovery companion from `docs/surmap/1-WIP/`
  - [ ] Test quality and fluent readability validated
  - [ ] Production readiness validated
  - [ ] Clean-code fixes applied
  - [ ] Changes validated against the plan
  - [ ] File-length gate passed
  - [ ] Lint, type-check, and tests green
  - [ ] Docs wrapped; rows and TODOs carried into the wrap commit and the PR body

## Initial Discovery

Full codebase exploration that grounded this plan: [2026-10-28-gps-anchored-snapshot-initial-discovery.md](./2026-10-28-gps-anchored-snapshot-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap** — new `surmap.map.snapshot` module and `tests/test_map_snapshot.py`

## Related Feature Documentation

- `docs/architecture.md` §6, §7, §12 — layered map, ENU origin, open GeoJSON decision. Not edited here.
- `docs/semantic-map-snapshot.md` — created at wrap; the schema consumers will read.

## Summary

Add a UTF-8 JSON snapshot of the semantic map. It is the export until GeoJSON is decided. Landmarks carry a stable id and an optional map-frame mask cloud. Moving tracks stay in `dynamic`.

## Background

Task 6 on PR #28. `GpsCheckpoint` has no caller. A later map Q&A feature and a 3D viewer need one documented JSON file, and task 5's mask clouds need a field to land in.

## Scope

- `build_snapshot(tracks, checkpoints, descriptions, model_ids, mask_points)` calls `classify_motion`.
- `write_snapshot` / `read_snapshot` round-trip UTF-8 JSON.
- Schema documented in `docs/semantic-map-snapshot.md`.
- Out of scope: GeoJSON, RTAB-Map writes, network, editing `README.md` or `docs/architecture.md`, the task 7 demo.

## Technical Changes

### State A (Current)

Tracks and GPS fixes exist as dataclasses. Motion classification exists. Nothing builds a semantic map, associates a fix, or writes an export. `GpsCheckpoint` is unused. There is no landmark id and nowhere to attach a mask cloud.

### State B (Target)

`surmap.map.snapshot` builds a `SemanticMapSnapshot`:

- `schema` is `surmap.semantic_map_snapshot.v1`.
- `origin` is the earliest `GpsCheckpoint` (`t_ns`, `lat`, `lon`, `alt`, `accuracy_m`), or `null`.
- `landmarks` holds tracks classified `static` or `unknown`. `dynamic` holds tracks classified `moving`. A moving track's points are not copied onto a landmark.
- Each entry has `id` (decimal `track_id`), `xyz` (latest map-frame centroid, x east / y north / z up), `lat`/`lon`/`alt` or `null`, `label`, `description`, `model_id`, `motion`, `t_ns`, `anchor_t_ns`, `offset_ns`, `observations`, and `mask_points`.
- `offset_ns` is `t_ns - anchor_t_ns` for the nearest fix by absolute time difference. Equal distances use the earlier fix. Both time fields are `null` when there is no fix.
- Geodetic position is the origin plus ENU metres, using 111320 m per degree of latitude and longitude scaled by cos(origin latitude). It is not the nearest fix's lat/lon.
- `mask_points` is `null` when omitted and a list of `{x,y,z}` when provided.
- `description` and `model_id` are empty strings when the caller does not pass them.
- A track with no observations is omitted. Duplicate `track_id`s raise `ValueError`.
- `write_snapshot` writes UTF-8 JSON. `read_snapshot` returns an equal snapshot.

### Delta (What's Changing)

#### surmap

- Add `src/surmap/map/__init__.py` and `src/surmap/map/snapshot.py`.
- Add `tests/test_map_snapshot.py`.
- Add `docs/semantic-map-snapshot.md` at wrap, plus history entries. Delete the `1-WIP` planning files at wrap.

## Verification

**Method:** V1-fail→pass — acceptance tests for the two-checkpoint static/moving split, the non-zero offset, and the read/write round-trip
**Command:** `uv run pytest -q tests/test_map_snapshot.py`
**Before:** module absent; the new tests fail on missing implementation. Suite baseline on `65a2fd6`: 468 passed, 5 skipped.
**After:** `tests/test_map_snapshot.py` passes, and `uv run pytest -q`, `uv run ruff check src tests`, `uv run ruff format --check src tests`, and `uv run mypy` are green.

## Testing Plan

### Testing Strategy

Unit tests through `build_snapshot`, `write_snapshot`, and `read_snapshot`. No hardware, no network, no SLAM. `classify_motion` runs for real. JSON is asserted both as the dataclass round-trip and as parsed keys, so a shared reader/writer bug cannot hide a renamed field.

### Testing Principles Applied

- One behaviour per test, Given / When / Then.
- Fixed timestamps and coordinates. No sleeps, no randomness.
- Builders hide checkpoint and track boilerplate.

### Coverage Requirements

The acceptance scenario, round-trip, missing fix, nearest-fix tie, origin-versus-nearest-fix geodesy, stable id, optional mask cloud on a static landmark and on a moving track, unknown motion, and UTF-8 text.

## Acceptance Tests

### surmap

- `test_static_landmark_is_anchored_and_the_moving_track_stays_dynamic` — two fixes, one still track, one track past the motion threshold; the static landmark has a non-zero `offset_ns`; the moving track is only under `dynamic`.
- `test_written_snapshot_reads_back_equal` — round-trip, including a non-ASCII description, and the file bytes are UTF-8.

## Decisions & Trade-offs

- **JSON, not GeoJSON.** Task 6 keeps GeoJSON open. The schema version lets a later exporter add a second file without pretending this one is GeoJSON.
- **Lat/lon comes from the origin plus ENU xyz, not from the nearest fix.** The nearest fix is only the time association. Snapping the position to that fix would drop the map-frame geometry §7 says to keep.
- **111320 m per degree.** Consumer GPS is metre-level (§7). The constant is exact at the equator for tests and is documented. Relative geometry stays in `xyz`.
- **Unknown tracks stay in `landmarks` with `motion: "unknown"`.** They are not moving, so they do not go in `dynamic`. Dropping them would hide a sighting from the viewer. Consumers that want confirmed static objects filter on `motion`.
- **`id` is the decimal track id.** Stable across a re-export of the same tracks, unique in one snapshot. Not a random uuid.
- **`mask_points` null versus `[]`.** Null means the caller did not attach a cloud. An empty list means a cloud was attached and contained no points.
- **Do not edit `docs/architecture.md` or `README.md`.** Task 8 says architecture is being edited on another branch. The schema doc states the current export without closing the GeoJSON decision.
- **No restructure prerequisite.** The new module is a new file. Nothing in `src/surmap/docs/todo/` blocks it. `code-issues/` has not been created for this package.

## Refactoring Needed

### From the Red step (Acceptance Test Creation)

- None yet.

## References

- Follow-up task 6, PR #28 comment 6479201212.
- Follow-up task 5, comment 6479199252 — map-frame mask points this schema stores and does not compute.
- `docs/architecture.md` §6, §7, §12.
