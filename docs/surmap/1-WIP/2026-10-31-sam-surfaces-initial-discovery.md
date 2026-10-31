# Initial Discovery: SAM surfaces — dense region points assigned to persistent object surfaces

**Changeset**: [2026-10-31-sam-surfaces.md](./2026-10-31-sam-surfaces.md)
**Date**: 2026-10-31
**Passes**: 1

## Combined Conclusions

- **Region points exist, per frame only.** `StreamRegionPoints` (#55) / `RegionPointSource`
  (`slam/regions.py`) answers one polygon on one frame with dense SGBM map-frame points. Nothing
  accumulates across frames — by contract.
- **The demo is where the station's SAM runs today.** `_Display._ready` (`demo/server.py`)
  releases each `sam` event and, when the backend is a `RegionPointSource`, immediately the
  `region` event from `RegionPlacer.region_event` (`demo/events.py`): per mask `track_id`,
  `label`, `status`, `points` (≤ 50 000).
- **The 3D layer is a browser round-trip and is replaced, not accumulated.** `cloud_script.py`
  `listenForRegions` → `setRegionLayer` POSTs `cloud_regions` to `/control`;
  `PlaybackControls.set_cloud_regions` replaces the tuple and bumps `cloud_version`; the player
  re-renders on a version change (`pose_changed`), and `render_cloud_view(regions=…)` splats each
  region 2×2 in `REGION_COLOURS[track_id % 4]`. Regions are never persisted.
- **SAM 3.1 ids are not stable.** `sam3_torch.py` propagates in 16-frame windows; object ids
  restart per window (changelog `2026-10-31-rtabmap-demo-sam31-video.md`). A surface identity
  cannot be the track id — the developer chose continuation by overlap with points earlier frames
  already assigned.
- **Persistence is `RunHistoryStore` (`demo/history.py`).** SQLite `demo-history.db`: `runs`,
  `frames`, `maps`, `detections`; `snapshot_at(run, seq)` joins the frame with the newest map at
  or before its `frame_id`. `_DemoHandler._stream` records `frame`/`map`/`detections`/`final`
  events; the `/runs/<id>/snapshot` handler re-renders `cloud_png` with the viewer's pose (no
  regions).
- **Constraints.** `demo/server.py` is 1819 lines with an open `oversized-file` code issue
  (Restructure: required) — this change must not grow it; new logic goes into new modules and
  the `cloud_regions` path it replaces is removed. `demo/page.py` (523) has the same record.
  Scope guardrail: the surface layer is layered on RTAB-Map's output, never written back.
  Moving objects: the architecture keeps them out of accumulated layers (§3.3/§6); the overlap
  rule alone does not classify motion — recorded as a decision.

## Exploration 1: region path, 3D render and history store — 2026-10-31

**Agent**: parent Grep/Read
**Scope**: `src/surmap/demo/`, `src/surmap/slam/regions.py`, `src/surmap/survey/`, `docs/`

### Sequence

1. `git log --oneline -8`, `git show --stat HEAD~1 HEAD` — what #55/#56 touched
2. Read `docs/architecture.md` — scope, layers (§6 `SemanticMap`), station/fuse roles
3. Read changelogs `2026-10-31-sam-region-points.md`, `…-rtabmap-demo-sam31-video.md`,
   `…-generic-test-console.md`
4. Read `demo/events.py`, `demo/history.py`, `slam/regions.py`
5. Grep `region|Region` in `demo/server.py`; read the render, `_Display`, `PlaybackControls`,
   `DemoPlayer.events`, `/control` and `_stream`
6. Grep `cloud_regions|regions=|REGION_COLOURS|listenForRegions|setRegionLayer` in `tests src scripts`
7. Read `src/surmap/docs/code-issues/oversized-file-demo-{server,page}.md`

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Grep | `region\|Region` | `demo/server.py` | `:55` import, `:371` `REGION_COLOURS`, `:407` `render_cloud_view(regions=)`, `:769` `RegionPlacer`, `:840` region event, `:954-962` controls, `:1684` `/control` parse |
| Grep | `record_\|history\|snapshot` | `demo/server.py` | `:1526` store, `:1588` `snapshot_at`, `:1758-1781` recording |
| Grep | `cloud_regions\|regions=\|REGION_COLOURS\|setRegionLayer` | `tests src scripts` | `tests/test_demo.py:703-736`, `tests/test_demo_regions.py:151-152` |

### Inspected files

#### `src/surmap/demo/server.py`

**Why**: where regions become a 3D layer.
**Excerpt**:

```python
    def set_cloud_regions(self, regions: tuple[tuple[int, NDArray[np.float32]], ...]) -> None:
        """Latest SAM regions to composite (replaced, never accumulated)."""
        with self._cloud_lock:
            self._cloud_regions = regions
            self._cloud_version += 1
...
        for event in sam_ready:
            frame_id = int(str(event.data["frame_id"]))
            yield DemoEvent("sam", event.data, jpeg=self._jpegs.get(frame_id, b""))
            if self._regions is not None:
                yield self._regions.region_event(event)
...
                    pose_changed = self._controls.cloud_version != self._cloud_version
                    if now - last_map_emit >= 0.33 or pose_changed:
```

#### `src/surmap/demo/events.py`

**Why**: the region event's shape.
**Excerpt**:

```python
            regions.append(
                {
                    "track_id": obj["track_id"],
                    "label": obj["label"],
                    "status": result.status.value,
                    "points": [[round(p.x, 3), round(p.y, 3), round(p.z, 3)] for p in points],
                }
            )
        return DemoEvent("region", {"frame_id": frame_id, "regions": regions})
```

#### `src/surmap/demo/history.py`

**Why**: where persistence lands.
**Excerpt**:

```python
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    t_ns INTEGER NOT NULL,
    objects TEXT NOT NULL
);
...
            map_row = self._db.execute(
                "SELECT * FROM maps WHERE run_id = ? AND frame_id <= ?"
                " ORDER BY frame_id DESC, id DESC LIMIT 1",
```

#### `src/surmap/demo/cloud_script.py`

**Why**: the browser round-trip to remove.
**Excerpt**:

```js
function setRegionLayer(regions) {
  postCloudDebounced({action: 'cloud_regions', regions: (regions || []).map((region) => ({
    track_id: region.track_id, points: region.points,
  }))});
}
```

### Findings

The surface logic has no I/O and belongs station-side (`survey/`, the `surmap_fuse` role in
architecture §4.2); the demo wires it between the `region` event and persistence, and owns the
layer server-side so the browser no longer posts points back.
