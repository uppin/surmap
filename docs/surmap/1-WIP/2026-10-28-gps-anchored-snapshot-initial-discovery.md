# Initial Discovery: GPS-anchored semantic map snapshot

**Changeset**: [2026-10-28-gps-anchored-snapshot.md](./2026-10-28-gps-anchored-snapshot.md)
**Date**: 2026-10-28
**Passes**: 1

## Combined Conclusions

SurMap has the §6 contracts (`GpsCheckpoint`, `ObjectTrack3D`, `Motion`) and
`classify_motion`, and no semantic-map export. `GpsCheckpoint` is defined in
`src/surmap/types.py` and has no caller under `src/` or `tests/`. There is
no `src/surmap/map/` package.

Architecture §6 layers the semantic map and never merges moving tracks into
the static object layer. §7 anchors the map in a local ENU frame whose
WGS84 origin is a GPS fix, and requires a recorded time offset whenever a
fix is associated with an observation. §12 leaves the export format open
(GeoJSON is a leaning, unconfirmed). Follow-up task 6
(PR #28 comment 6479201212) chooses a plain JSON file as the export until
that decision is made, in `src/surmap/map/snapshot.py` and
`tests/test_map_snapshot.py`.

Task 5 (comment 6479199252) will produce map-frame points from a SAM mask
via `to_map_frame`. It is a separate branch and is not in this tree. The
snapshot has to be able to carry that cloud later without a schema break:
an optional `mask_points` list of map-frame xyz on each landmark.

No open TODO under `src/surmap/docs/todo/` mentions GPS, landmarks, or map
export. `src/surmap/docs/code-issues/` does not exist. Nothing in this
change's path is a prerequisite.

`docs/architecture.md` is called out by follow-up task 8 as in flux on
`feat/PX4_sitl`. This change does not edit it. The schema lives in a new
stable doc under `docs/`. `README.md` and `HACKATHON.md` are not on this
branch's edit list (`HACKATHON.md` is not on `main`).

Baseline before any snapshot code: `uv run pytest -q` → 468 passed, 5 skipped.

## Exploration 1: snapshot inputs and where a map export would land — 2026-10-28

**Agent**: parent Grep/Glob/Read
**Scope**: contracts, motion classification, architecture §6–§7 and §12, follow-up tasks 5–7, package docs

### Sequence

1. `gh api` comment 6479201212 — the task text this change implements.
2. `gh api` issue comments on PR 28 — neighbouring tasks, especially mask clouds (task 5) and the demo that will call `write_snapshot` (task 7).
3. Glob `src/surmap/**/*.py` and Grep `GpsCheckpoint|classify_motion|SemanticMap|Landmark` — find the contracts and confirm nothing writes a map snapshot.
4. Read `src/surmap/types.py`, `src/surmap/motion.py`, `src/surmap/geometry.py` — inputs the snapshot can call without a new model.
5. Read `docs/architecture.md` from §5 through §12 — layers, ENU origin, offset rule, open GeoJSON decision.
6. Glob `docs/**/*`, `HACKATHON.md`, `src/surmap/map/**` — doc home and confirmation the map package does not exist.
7. Glob `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/` — deferred-work cross-check.
8. `uv run pytest -q` — baseline on this commit's parent (`65a2fd6`).

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Grep | `GpsCheckpoint` | `src`, `tests` | definition only, `src/surmap/types.py:50` |
| Grep | `classify_motion` | `src/surmap` | `src/surmap/motion.py:14`; tests in `tests/test_motion.py` |
| Grep | `SemanticMap\|Landmark` | `src` | design names only; no Python type |
| Glob | `src/surmap/map/**` | repo | no files |
| Glob | `HACKATHON.md` | repo | absent on `main` |
| Glob | `src/surmap/docs/code-issues/**` | repo | directory absent |
| Glob | `src/surmap/docs/todo/*` | repo | six moving-object TODOs, none about GPS or export |

### Inspected files

#### `src/surmap/types.py`

**Why**: the checkpoint and track shapes the snapshot must consume.
**Excerpt**:

```python
@dataclass(frozen=True)
class GpsCheckpoint:
    t_ns: int
    lat: float
    lon: float
    alt: float
    accuracy_m: float

@dataclass
class ObjectTrack3D:
    track_id: int
    label: str
    observations: list[ObjectPoints] = field(default_factory=list)
    motion: Motion = Motion.UNKNOWN
```

`ObjectPoints` already carries map-frame `centroid` and `t_ns`. `Motion` values are `"static"`, `"moving"`, `"unknown"`.

#### `src/surmap/motion.py`

**Why**: the classifier the task says to call, including the default threshold.
**Excerpt**:

```python
def classify_motion(
    track: ObjectTrack3D,
    threshold_m: float = 0.5,
    min_observations: int = 2,
) -> Motion:
    ...
    displacement = (track.observations[-1].centroid - track.observations[0].centroid).norm()
    return Motion.MOVING if displacement > threshold_m else Motion.STATIC
```

One observation returns `Motion.UNKNOWN`. The stored `track.motion` field is not consulted.

#### `docs/architecture.md` §6–§7 and §12

**Why**: what a semantic-map snapshot is allowed to merge, and how GPS anchoring is specified.
**Excerpt**:

```text
2. Static object layer: accumulated ObjectPoints of tracks classified static …
3. Dynamic layer: ObjectTrack3Ds classified moving … excluded from layers 1–2 by construction.
…
Anchored to GPS; internal coordinates in a local ENU frame with a recorded WGS84 origin.
…
No GPS reading is ever snapped to a frame without recording the offset.
…
Map export format (GeoJSON-flavoured JSON is the current leaning, unconfirmed).
```

#### `src/surmap/geometry.py`

**Why**: whether a geodetic conversion already exists. It does not. `to_map_frame` only rotates a camera-frame point into the map frame. Task 5 owns mask projection; this change only stores the resulting xyz list.

### Findings

- The snapshot's inputs are `ObjectTrack3D` plus `GpsCheckpoint`. Motion comes from `classify_motion`, not from `track.motion`.
- Origin and nearest-fix association are different jobs. The origin is the earliest fix and defines the ENU frame. The nearest fix by `t_ns` is the time association and produces `offset_ns`. A landmark's lat/lon/alt is the origin plus its map-frame xyz, not the nearest fix's coordinates.
- Moving tracks are a separate `dynamic` list. Their points, including a mask cloud, stay on that entry.
- `id` can be the decimal track id: unique inside one session snapshot and stable if the same tracks are exported again.
- No network, no new dependency. JSON is stdlib. Tests are unit-level with `tmp_path`.
